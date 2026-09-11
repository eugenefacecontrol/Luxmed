import html
import base64
import json
import logging
import os
import re
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse

import requests


LOGGER = logging.getLogger("luxmed-bot")
STOP = False


def env(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_list(*names: str) -> list[str]:
    values: list[str] = []
    for name in names:
        raw = os.getenv(name, "")
        for item in raw.replace(";", ",").split(","):
            stripped = item.strip()
            if stripped and stripped not in values:
                values.append(stripped)
    return values


@dataclass
class SearchJob:
    name: str
    request_url: str
    doctor_regex: str | None = None
    clinic_regex: str | None = None
    time_from: str | None = None
    time_to: str | None = None
    match_text_regex: str | None = None


def parse_jobs_from_env() -> list[SearchJob]:
    jobs_json = env("LUXMED_JOBS_JSON")
    if jobs_json:
        data = json.loads(jobs_json)
        if not isinstance(data, list):
            raise RuntimeError("LUXMED_JOBS_JSON must be a JSON array.")

        jobs: list[SearchJob] = []
        for index, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                raise RuntimeError(f"LUXMED_JOBS_JSON item {index} must be an object.")
            request_url = str(item.get("request_url") or item.get("url") or "").strip()
            if not request_url:
                raise RuntimeError(f"LUXMED_JOBS_JSON item {index} is missing request_url.")
            jobs.append(
                SearchJob(
                    name=str(item.get("name") or f"job-{index}"),
                    request_url=request_url,
                    doctor_regex=item.get("doctor_regex") or None,
                    clinic_regex=item.get("clinic_regex") or None,
                    time_from=item.get("time_from") or None,
                    time_to=item.get("time_to") or None,
                    match_text_regex=item.get("match_text_regex") or None,
                )
            )
        return jobs

    request_url = env("LUXMED_REQUEST_URL")
    if not request_url:
        raise RuntimeError("Missing LUXMED_REQUEST_URL or LUXMED_JOBS_JSON.")

    return [
        SearchJob(
            name=env("LUXMED_JOB_NAME", "default") or "default",
            request_url=request_url,
            doctor_regex=env("LUXMED_DOCTOR_REGEX") or None,
            clinic_regex=env("LUXMED_CLINIC_REGEX") or None,
            time_from=env("LUXMED_TIME_FROM") or None,
            time_to=env("LUXMED_TIME_TO") or None,
            match_text_regex=env("LUXMED_MATCH_TEXT_REGEX") or None,
        )
    ]


@dataclass
class Settings:
    telegram_bot_token: str
    telegram_target_ids: list[str]
    luxmed_login: str | None
    luxmed_password: str | None
    luxmed_cookie_header: str | None
    luxmed_base_uri: str
    jobs: list[SearchJob]
    poll_interval_seconds: int
    notify_on_every_match: bool
    request_timeout_seconds: int
    auth_expiry_warn_minutes: int
    state_file: str

    @classmethod
    def from_env(cls) -> "Settings":
        telegram_target_ids = env_list("TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_IDS", "TELEGRAM_USER_IDS")
        if not telegram_target_ids:
            raise RuntimeError("Missing TELEGRAM_CHAT_ID, TELEGRAM_CHAT_IDS, or TELEGRAM_USER_IDS.")

        return cls(
            telegram_bot_token=env("TELEGRAM_BOT_TOKEN", required=True),
            telegram_target_ids=telegram_target_ids,
            luxmed_login=env("LUXMED_LOGIN") or None,
            luxmed_password=env("LUXMED_PASSWORD") or None,
            luxmed_cookie_header=env("LUXMED_COOKIE_HEADER") or None,
            luxmed_base_uri=env("LUXMED_BASE_URI", "https://portalpacjenta.luxmed.pl"),
            jobs=parse_jobs_from_env(),
            poll_interval_seconds=int(env("POLL_INTERVAL_SECONDS", "60")),
            notify_on_every_match=env_bool("NOTIFY_ON_EVERY_MATCH", False),
            request_timeout_seconds=int(env("REQUEST_TIMEOUT_SECONDS", "30")),
            auth_expiry_warn_minutes=int(env("AUTH_EXPIRY_WARN_MINUTES", "2")),
            state_file=env("STATE_FILE", "/data/luxmed_state.json"),
        )


class StateStore:
    def __init__(self, path: str) -> None:
        self.path = path

    def load(self) -> dict[str, str]:
        if not os.path.exists(self.path):
            return {}

        with open(self.path, "r", encoding="utf-8") as state_file:
            data = json.load(state_file)

        if not isinstance(data, dict):
            return {}

        return {str(key): str(value) for key, value in data.items()}

    def save(self, data: dict[str, str]) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        temp_path = f"{self.path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as state_file:
            json.dump(data, state_file, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temp_path, self.path)

    def get(self, key: str, default: str) -> str:
        return self.load().get(key, default)

    def set(self, key: str, value: str) -> None:
        data = self.load()
        data[key] = value
        data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.save(data)


class Telegram:
    def __init__(self, token: str, target_ids: list[str]) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.target_ids = target_ids
        self.offset = 0

    def send(self, text: str, reply_markup: dict[str, Any] | None = None) -> None:
        for target_id in self.target_ids:
            payload: dict[str, Any] = {
                "chat_id": target_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup
            response = requests.post(
                f"{self.base_url}/sendMessage",
                json=payload,
                timeout=20,
            )
            if not response.ok:
                raise RuntimeError(f"Telegram sendMessage failed for {target_id}: HTTP {response.status_code}; {response.text[:500]}")

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> None:
        response = requests.post(
            f"{self.base_url}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text},
            timeout=20,
        )
        if not response.ok:
            LOGGER.warning("Telegram answerCallbackQuery failed: HTTP %s; %s", response.status_code, response.text[:500])

    def set_my_commands(self) -> None:
        commands = [
            {"command": "menu", "description": "Show control buttons"},
            {"command": "status", "description": "Show last monitor status"},
            {"command": "check", "description": "Check all Luxmed jobs now"},
            {"command": "jobs", "description": "List configured Luxmed searches"},
            {"command": "config", "description": "Show current bot config"},
            {"command": "interval", "description": "Set poll interval in seconds"},
            {"command": "live", "description": "Enable live status updates"},
            {"command": "live_off", "description": "Disable live status updates"},
            {"command": "notify_once", "description": "Notify only when results change"},
            {"command": "notify_every", "description": "Notify on every matching check"},
            {"command": "auth", "description": "Show Luxmed auth status"},
            {"command": "login", "description": "Refresh Luxmed auth"},
            {"command": "help", "description": "Show help"},
        ]
        response = requests.post(
            f"{self.base_url}/setMyCommands",
            json={"commands": commands},
            timeout=20,
        )
        if not response.ok:
            LOGGER.warning("Telegram setMyCommands failed: HTTP %s; %s", response.status_code, response.text[:500])

    def poll_commands(self) -> list[str]:
        response = requests.get(
            f"{self.base_url}/getUpdates",
            params={"offset": self.offset, "timeout": 0, "allowed_updates": json.dumps(["message", "callback_query"])},
            timeout=20,
        )
        if not response.ok:
            raise RuntimeError(f"Telegram getUpdates failed: HTTP {response.status_code}; {response.text[:500]}")

        commands: list[str] = []
        for update in response.json().get("result", []):
            self.offset = max(self.offset, update["update_id"] + 1)
            callback_query = update.get("callback_query")
            if isinstance(callback_query, dict):
                callback_id = str(callback_query.get("id") or "")
                user_id = str(callback_query.get("from", {}).get("id"))
                message = callback_query.get("message") or {}
                chat_id = str(message.get("chat", {}).get("id"))
                if chat_id not in self.target_ids and user_id not in self.target_ids:
                    continue
                data = str(callback_query.get("data") or "").strip()
                if data.startswith("/"):
                    commands.append(data)
                    if callback_id:
                        self.answer_callback_query(callback_id)
                continue

            message = update.get("message") or {}
            chat_id = str(message.get("chat", {}).get("id"))
            user_id = str(message.get("from", {}).get("id"))
            if chat_id not in self.target_ids and user_id not in self.target_ids:
                continue
            text = (message.get("text") or "").strip()
            if text.startswith("/"):
                commands.append(text)
        return commands


def signal_handler(_signum: int, _frame: Any) -> None:
    global STOP
    STOP = True


def cookie_dict(cookie_header: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in cookie_header.split(";"):
        part = part.strip()
        if not part:
            continue
        name, _, value = part.partition("=")
        cookies[name.strip()] = value.strip()
    return cookies


def cookie_header_from_dict(cookies: dict[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookies.items() if name)


def upsert_cookie(cookie_header: str, name: str, value: str) -> str:
    cookies = cookie_dict(cookie_header)
    cookies[name] = value.strip()
    return cookie_header_from_dict(cookies)


def decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("Authorization-Token is not a JWT")

    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
    return json.loads(decoded)


def auth_token_status(cookie_header: str, warn_minutes: int) -> tuple[str, str]:
    cookies = cookie_dict(cookie_header)
    token = cookies.get("Authorization-Token")
    if not token:
        return "missing", "Authorization-Token is missing. Bot will try to generate it when Luxmed credentials are configured."

    try:
        payload = decode_jwt_payload(token)
    except Exception as exc:
        return "invalid", f"Authorization-Token could not be decoded: {exc}"

    exp = payload.get("exp")
    if not isinstance(exp, int):
        return "unknown", "Authorization-Token has no readable exp claim."

    now = datetime.now(timezone.utc)
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    seconds_left = int((expires_at - now).total_seconds())
    expires_text = expires_at.isoformat(timespec="seconds")

    if seconds_left <= 0:
        return f"expired:{exp}", f"Luxmed Authorization-Token expired at {expires_text}. Refresh .env from browser."

    warn_seconds = warn_minutes * 60
    if seconds_left <= warn_seconds:
        return (
            f"expiring:{exp}",
            f"Luxmed Authorization-Token expires soon: {expires_text} ({seconds_left}s left). Bot will try to refresh it.",
        )

    return f"valid:{exp}", f"Luxmed Authorization-Token valid until {expires_text} ({seconds_left}s left)."


def luxmed_headers(request_url: str, cookie_header: str) -> dict[str, str]:
    parsed = urlparse(request_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    cookies = cookie_dict(cookie_header)
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru,en;q=0.9,be;q=0.8,pl;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": f"{origin}/PatientPortal/NewPortal/Page/Reservation/Results",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
    }
    if cookie_header:
        headers["Cookie"] = cookie_header

    xsrf = cookies.get("XSRF-TOKEN")
    if xsrf:
        headers["X-XSRF-TOKEN"] = xsrf
        headers["xsrf-token"] = xsrf
    return headers


def login_luxmed(settings: Settings, cookie_header: str) -> str:
    if not settings.luxmed_login or not settings.luxmed_password:
        raise RuntimeError("LUXMED_LOGIN and LUXMED_PASSWORD are required for automatic token refresh.")

    base_uri = settings.luxmed_base_uri.rstrip("/")
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru,en;q=0.9,be;q=0.8,pl;q=0.7",
        "Cache-Control": "no-cache",
        "Origin": base_uri,
        "Pragma": "no-cache",
        "Referer": f"{base_uri}/PatientPortal/NewPortal/Page/Account/Login?returnUrl=%2FPage%2FReservation%2FResults",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
    }
    if cookie_header:
        headers["Cookie"] = cookie_header

    response = requests.post(
        f"{base_uri}/PatientPortal/Account/LogIn",
        headers=headers,
        json={"login": settings.luxmed_login, "password": settings.luxmed_password},
        timeout=settings.request_timeout_seconds,
    )
    response.raise_for_status()

    payload = response.json()
    if not payload.get("succeded") or not payload.get("token"):
        raise RuntimeError(payload.get("errorMessage") or "Luxmed login failed without errorMessage.")

    return str(payload["token"])


def fetch_luxmed(settings: Settings, job: SearchJob, cookie_header: str) -> tuple[Any, str]:
    response = requests.get(
        job.request_url,
        headers=luxmed_headers(job.request_url, cookie_header),
        timeout=settings.request_timeout_seconds,
    )
    response.raise_for_status()

    text = response.text
    try:
        return response.json(), text
    except ValueError:
        return None, text


def doctor_name(term: dict[str, Any]) -> str:
    doctor = term.get("doctor")
    if not isinstance(doctor, dict):
        return ""

    parts = [
        str(doctor.get("academicTitle") or "").strip(),
        str(doctor.get("firstName") or "").strip(),
        str(doctor.get("lastName") or "").strip(),
    ]
    return " ".join(part for part in parts if part)


def normalize_term(term: dict[str, Any], day: dict[str, Any], service_id: Any) -> dict[str, Any]:
    return {
        "dateTimeFrom": term.get("dateTimeFrom"),
        "dateTimeTo": term.get("dateTimeTo"),
        "doctorName": doctor_name(term),
        "doctorId": (term.get("doctor") or {}).get("id") if isinstance(term.get("doctor"), dict) else None,
        "clinic": term.get("clinic"),
        "clinicGroup": term.get("clinicGroup"),
        "clinicId": term.get("clinicId"),
        "roomId": term.get("roomId"),
        "serviceId": term.get("serviceId") or service_id,
        "scheduleId": term.get("scheduleId"),
        "isTelemedicine": term.get("isTelemedicine"),
        "day": day.get("day"),
        "correlationId": day.get("correlationId"),
        "raw": term,
    }


def term_search_text(term: dict[str, Any]) -> str:
    return " ".join(
        str(term.get(key) or "")
        for key in ("dateTimeFrom", "dateTimeTo", "doctorName", "clinic", "clinicGroup", "serviceId", "scheduleId")
    )


def extract_terms(payload: Any, raw_text: str) -> list[dict[str, Any]]:
    if payload is None:
        stripped = re.sub(r"<[^>]+>", " ", raw_text)
        stripped = re.sub(r"\s+", " ", stripped).strip()
        return [{"rawText": stripped[:1200]}] if stripped else []

    if isinstance(payload, dict):
        service = payload.get("termsForService")
        if isinstance(service, dict):
            service_id = service.get("serviceVariantId")
            normalized: list[dict[str, Any]] = []
            for day in service.get("termsForDays") or []:
                if not isinstance(day, dict):
                    continue
                for term in day.get("terms") or []:
                    if isinstance(term, dict):
                        normalized.append(normalize_term(term, day, service_id))
            return normalized

        terms = payload.get("terms")
        if isinstance(terms, list):
            return [normalize_term(term, {}, None) for term in terms if isinstance(term, dict)]

    if isinstance(payload, list):
        return [normalize_term(term, {}, None) for term in payload if isinstance(term, dict)]

    return []


def time_value(date_time: Any) -> str | None:
    if not date_time:
        return None

    match = re.search(r"T(\d{2}:\d{2})", str(date_time))
    if match:
        return match.group(1)

    match = re.search(r"\b(\d{2}:\d{2})\b", str(date_time))
    return match.group(1) if match else None


def matches_time_window(term: dict[str, Any], job: SearchJob) -> bool:
    if not job.time_from and not job.time_to:
        return True

    value = time_value(term.get("dateTimeFrom"))
    if not value:
        return False

    if job.time_from and value < job.time_from:
        return False

    if job.time_to and value > job.time_to:
        return False

    return True


def matches_filters(terms: list[dict[str, Any]], raw_text: str, job: SearchJob) -> list[dict[str, Any]]:
    candidates = terms or []

    if job.doctor_regex:
        pattern = re.compile(job.doctor_regex, re.IGNORECASE)
        candidates = [term for term in candidates if pattern.search(term_search_text(term))]

    if job.clinic_regex:
        pattern = re.compile(job.clinic_regex, re.IGNORECASE)
        candidates = [term for term in candidates if pattern.search(term_search_text(term))]

    candidates = [term for term in candidates if matches_time_window(term, job)]

    if job.match_text_regex:
        pattern = re.compile(job.match_text_regex, re.IGNORECASE)
        candidates = [term for term in candidates if pattern.search(term_search_text(term))]
        if not candidates and pattern.search(raw_text):
            candidates = [{"rawText": raw_text[:1200]}]

    return candidates


def signature(matches: list[dict[str, Any]]) -> str:
    normalized = json.dumps(
        [
            {
                "dateTimeFrom": term.get("dateTimeFrom"),
                "doctorId": term.get("doctorId"),
                "clinicId": term.get("clinicId"),
                "roomId": term.get("roomId"),
                "serviceId": term.get("serviceId"),
                "scheduleId": term.get("scheduleId"),
            }
            for term in matches
        ],
        ensure_ascii=False,
        sort_keys=True,
    )
    return str(hash(normalized))


def results_page_url(settings: Settings) -> str:
    return f"{settings.luxmed_base_uri.rstrip('/')}/PatientPortal/NewPortal/Page/Reservation/Results"


def request_params(job: SearchJob) -> dict[str, str]:
    return dict(parse_qsl(urlparse(job.request_url).query, keep_blank_values=True))


def term_reference_url(term: dict[str, Any], settings: Settings, job: SearchJob) -> str:
    params = request_params(job)
    slot_params = {
        "dateTimeFrom": term.get("dateTimeFrom"),
        "dateTimeTo": term.get("dateTimeTo"),
        "doctorId": term.get("doctorId"),
        "clinicId": term.get("clinicId"),
        "roomId": term.get("roomId"),
        "serviceId": term.get("serviceId"),
        "scheduleId": term.get("scheduleId"),
        "correlationId": term.get("correlationId"),
        "referralId": params.get("referralId"),
        "referralTypeId": params.get("referralTypeId"),
        "processId": params.get("processId"),
    }
    fragment = urlencode({key: str(value) for key, value in slot_params.items() if value not in (None, "")})
    return f"{results_page_url(settings)}#{fragment}"


def term_identifier(term: dict[str, Any]) -> str:
    parts = [
        f"serviceId={term.get('serviceId') or '?'}",
        f"scheduleId={term.get('scheduleId') or '?'}",
        f"roomId={term.get('roomId') or '?'}",
        f"clinicId={term.get('clinicId') or '?'}",
        f"doctorId={term.get('doctorId') or '?'}",
    ]
    return "; ".join(parts)


def format_term(term: dict[str, Any], settings: Settings, job: SearchJob) -> str:
    if term.get("rawText"):
        return html.escape(str(term["rawText"]))

    doctor = term.get("doctorName") or "Unknown doctor"
    clinic = term.get("clinic") or term.get("clinicGroup") or "Unknown clinic"
    when_from = term.get("dateTimeFrom") or "?"
    when_to = term.get("dateTimeTo") or "?"
    visit_type = "telemedicine" if term.get("isTelemedicine") else "facility"
    slot_url = term_reference_url(term, settings, job)

    return (
        f"<b>{html.escape(str(when_from))} - {html.escape(str(when_to))}</b>\n"
        f"{html.escape(str(doctor))}\n"
        f"{html.escape(str(clinic))}\n"
        f"<code>{html.escape(visit_type)}; {html.escape(term_identifier(term))}</code>\n"
        f"<a href=\"{html.escape(slot_url)}\">Open Luxmed result</a>"
    )


def format_match_message(matches: list[dict[str, Any]], settings: Settings, job: SearchJob) -> str:
    params = request_params(job)
    service = params.get("serviceVariantId", "?")
    date_from = params.get("searchDateFrom", "?")
    date_to = params.get("searchDateTo", "?")
    referral_id = params.get("referralId", "?")
    process_id = params.get("processId", "?")

    preview = "\n\n".join(format_term(term, settings, job) for term in matches[:8])
    if len(matches) > 8:
        preview += f"\n\n...and {len(matches) - 8} more"

    return (
        "<b>Luxmed: found appointment windows</b>\n"
        f"Job: <code>{html.escape(job.name)}</code>\n"
        f"ServiceVariantId: <code>{html.escape(service)}</code>\n"
        f"ReferralId: <code>{html.escape(referral_id)}</code>\n"
        f"ProcessId: <code>{html.escape(process_id)}</code>\n"
        f"Dates: <code>{html.escape(date_from)}</code> - <code>{html.escape(date_to)}</code>\n"
        f"Matches: <code>{len(matches)}</code>\n\n"
        f"{preview[:3300]}\n\n"
        f"Results page: {html.escape(results_page_url(settings))}\n"
        f"API request: {html.escape(job.request_url)}"
    )


def run_once(settings: Settings, job: SearchJob, cookie_header: str) -> tuple[int, list[dict[str, Any]]]:
    payload, raw_text = fetch_luxmed(settings, job, cookie_header)
    terms = extract_terms(payload, raw_text)
    matches = matches_filters(terms, raw_text, job)
    return len(terms), matches


def active_cookie_header(settings: Settings, state: StateStore) -> str:
    return state.get("luxmed_cookie_header", settings.luxmed_cookie_header or "")


def refresh_auth_token(settings: Settings, state: StateStore) -> str:
    cookie_header = active_cookie_header(settings, state)
    token = login_luxmed(settings, cookie_header)
    cookie_header = upsert_cookie(cookie_header, "Authorization-Token", token)
    state.set("luxmed_cookie_header", cookie_header)
    return cookie_header


def main_menu_markup() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Status", "callback_data": "/status"},
                {"text": "Check now", "callback_data": "/check"},
            ],
            [
                {"text": "Jobs", "callback_data": "/jobs"},
                {"text": "Config", "callback_data": "/config"},
            ],
            [
                {"text": "Interval 1m", "callback_data": "/interval 60"},
                {"text": "Interval 1h", "callback_data": "/interval 3600"},
            ],
            [
                {"text": "Live 1h", "callback_data": "/live 3600"},
                {"text": "Live off", "callback_data": "/live_off"},
            ],
            [
                {"text": "Notify once", "callback_data": "/notify_once"},
                {"text": "Notify every", "callback_data": "/notify_every"},
            ],
            [
                {"text": "Refresh auth", "callback_data": "/login"},
                {"text": "Menu", "callback_data": "/menu"},
            ],
        ]
    }


def help_text() -> str:
    return (
        "Luxmed monitor controls:\n"
        "/status - last status\n"
        "/check - check all jobs now\n"
        "/jobs - show configured searches\n"
        "/config - show config\n"
        "/interval 3600 - set poll interval\n"
        "/live 3600 - enable live status and set interval\n"
        "/live_off - disable live status\n"
        "/notify_once - notify only when results change\n"
        "/notify_every - notify on every matching check\n"
        "/login - refresh Luxmed auth"
    )


def state_bool(state: StateStore, key: str, default: bool = False) -> bool:
    value = state.get(key, "true" if default else "false")
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def active_poll_interval(settings: Settings, state: StateStore) -> int:
    raw = state.get("poll_interval_seconds", str(settings.poll_interval_seconds))
    try:
        return max(10, int(raw))
    except ValueError:
        return settings.poll_interval_seconds


def active_notify_on_every_match(settings: Settings, state: StateStore) -> bool:
    raw = state.get("notify_on_every_match", "true" if settings.notify_on_every_match else "false")
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def set_poll_interval(state: StateStore, seconds: int) -> None:
    state.set("poll_interval_seconds", str(max(10, seconds)))


def format_jobs(settings: Settings) -> str:
    lines = ["Luxmed jobs:"]
    for index, job in enumerate(settings.jobs, start=1):
        params = request_params(job)
        lines.append(
            "\n"
            f"{index}. <b>{html.escape(job.name)}</b>\n"
            f"serviceVariantId=<code>{html.escape(params.get('serviceVariantId', '?'))}</code>; "
            f"referralId=<code>{html.escape(params.get('referralId', '?'))}</code>\n"
            f"doctor=<code>{html.escape(job.doctor_regex or '-')}</code>; "
            f"clinic=<code>{html.escape(job.clinic_regex or '-')}</code>; "
            f"time=<code>{html.escape(job.time_from or '-')}</code>-<code>{html.escape(job.time_to or '-')}</code>"
        )
    return "\n".join(lines)


def check_all_jobs(settings: Settings, cookie_header: str) -> list[tuple[SearchJob, int, list[dict[str, Any]]]]:
    results: list[tuple[SearchJob, int, list[dict[str, Any]]]] = []
    for job in settings.jobs:
        total, matches = run_once(settings, job, cookie_header)
        results.append((job, total, matches))
    return results


def format_live_status(
    checked_at: str,
    results: list[tuple[SearchJob, int, list[dict[str, Any]]]],
    interval: int,
    auth_key: str,
) -> str:
    lines = [
        "<b>Luxmed live status</b>",
        f"Checked: <code>{html.escape(checked_at)}</code>",
        f"Next interval: <code>{interval}s</code>",
        f"Auth: <code>{html.escape(auth_key.split(':', 1)[0])}</code>",
        "",
    ]
    for job, total, matches in results:
        lines.append(f"{html.escape(job.name)}: terms=<code>{total}</code>, matches=<code>{len(matches)}</code>")
    return "\n".join(lines)


def handle_command(
    command_text: str,
    settings: Settings,
    state: StateStore,
    telegram: Telegram,
    auth_message: str,
    last_status: str,
) -> str | None:
    command, _, argument = command_text.partition(" ")
    command = command.lower()
    argument = argument.strip()

    if command in {"/start", "/help"}:
        telegram.send(help_text(), reply_markup=main_menu_markup())
    elif command == "/auth":
        telegram.send(html.escape(auth_message))
    elif command == "/status":
        telegram.send(last_status)
    elif command == "/jobs":
        telegram.send(format_jobs(settings))
    elif command in {"/interval", "/set_interval"}:
        if not argument or not argument.isdigit():
            telegram.send("Usage: /interval 3600")
            return None
        set_poll_interval(state, int(argument))
        telegram.send(f"Poll interval updated to <code>{active_poll_interval(settings, state)}s</code>.")
    elif command == "/live":
        if argument:
            if not argument.isdigit():
                telegram.send("Usage: /live [seconds]")
                return None
            set_poll_interval(state, int(argument))
        state.set("live_status_enabled", "true")
        telegram.send(f"Live status enabled. Interval: <code>{active_poll_interval(settings, state)}s</code>.")
    elif command in {"/live_off", "/stop_live"}:
        state.set("live_status_enabled", "false")
        telegram.send("Live status disabled.")
    elif command in {"/notify_once", "/notify_changed"}:
        state.set("notify_on_every_match", "false")
        telegram.send("Notify mode: only when matching results change.", reply_markup=main_menu_markup())
    elif command in {"/notify_every", "/notify_always"}:
        state.set("notify_on_every_match", "true")
        telegram.send("Notify mode: every check with matching results.", reply_markup=main_menu_markup())
    elif command == "/config":
        telegram.send(
            "Luxmed monitor config:\n"
            f"Interval: <code>{active_poll_interval(settings, state)}s</code>\n"
            f"Auth expiry warning: <code>{settings.auth_expiry_warn_minutes}m</code>\n"
            f"Auto login: <code>{'on' if settings.luxmed_login and settings.luxmed_password else 'off'}</code>\n"
            f"Jobs: <code>{len(settings.jobs)}</code>\n"
            f"Live status: <code>{'on' if state_bool(state, 'live_status_enabled') else 'off'}</code>\n"
            f"Notify every match: <code>{'on' if active_notify_on_every_match(settings, state) else 'off'}</code>\n"
            f"State file: <code>{html.escape(settings.state_file)}</code>"
        )
    elif command == "/menu":
        telegram.send("Luxmed monitor menu", reply_markup=main_menu_markup())
    elif command == "/set_cookie":
        if not argument:
            telegram.send("Usage: /set_cookie Authorization-Token=...; XSRF-TOKEN=...")
            return
        state.set("luxmed_cookie_header", argument)
        telegram.send("Luxmed cookie header updated.")
    elif command in {"/set_auth", "/set_token"}:
        if not argument:
            telegram.send("Usage: /set_auth <Authorization-Token>")
            return
        cookie_header = upsert_cookie(active_cookie_header(settings, state), "Authorization-Token", argument)
        state.set("luxmed_cookie_header", cookie_header)
        telegram.send("Luxmed Authorization-Token updated.")
    elif command == "/set_xsrf":
        if not argument:
            telegram.send("Usage: /set_xsrf <XSRF-TOKEN>")
            return
        cookie_header = upsert_cookie(active_cookie_header(settings, state), "XSRF-TOKEN", argument)
        state.set("luxmed_cookie_header", cookie_header)
        telegram.send("Luxmed XSRF-TOKEN updated.")
    elif command == "/set_refresh":
        if not argument:
            telegram.send("Usage: /set_refresh <RefreshToken>")
            return
        cookie_header = upsert_cookie(active_cookie_header(settings, state), "RefreshToken", argument)
        state.set("luxmed_cookie_header", cookie_header)
        telegram.send("Luxmed RefreshToken updated.")
    elif command == "/set_lx":
        if not argument:
            telegram.send("Usage: /set_lx <LXToken>")
            return
        cookie_header = upsert_cookie(active_cookie_header(settings, state), "LXToken", argument)
        state.set("luxmed_cookie_header", cookie_header)
        telegram.send("Luxmed LXToken updated.")
    elif command == "/login":
        cookie_header = refresh_auth_token(settings, state)
        _, auth_message = auth_token_status(cookie_header, settings.auth_expiry_warn_minutes)
        telegram.send(f"Luxmed token refreshed.\n{html.escape(auth_message)}")

    return None


def process_telegram_commands(
    settings: Settings,
    state: StateStore,
    telegram: Telegram,
    auth_message: str,
    last_status: str,
) -> str:
    for command_text in telegram.poll_commands():
        command = command_text.split(maxsplit=1)[0].lower()
        if command == "/check":
            cookie_header = active_cookie_header(settings, state)
            results = check_all_jobs(settings, cookie_header)
            checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            last_status = format_live_status(checked_at, results, active_poll_interval(settings, state), "manual-check")
            sent_match = False
            for job, _total, matches in results:
                if matches:
                    telegram.send(format_match_message(matches, settings, job))
                    sent_match = True
            if not sent_match:
                summary = ", ".join(f"{job.name}: terms={total}, matches=0" for job, total, _ in results)
                telegram.send(f"Manual check: no matching appointment windows right now.\n{html.escape(summary)}")
        else:
            handle_command(command_text, settings, state, telegram, auth_message, last_status)
    return last_status


def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    state = StateStore(settings.state_file)
    telegram = Telegram(settings.telegram_bot_token, settings.telegram_target_ids)
    last_signatures: dict[str, str] = {}
    last_status = "Starting"
    last_auth_warning_key = ""
    last_http_auth_warning_key = ""

    telegram.set_my_commands()
    telegram.send(f"Luxmed monitor started. Jobs: <code>{len(settings.jobs)}</code>.", reply_markup=main_menu_markup())

    while not STOP:
        interval = active_poll_interval(settings, state)
        try:
            cookie_header = active_cookie_header(settings, state)
            auth_key, auth_message = auth_token_status(cookie_header, settings.auth_expiry_warn_minutes)
            if auth_key.startswith(("missing", "invalid", "expired", "expiring")):
                if settings.luxmed_login and settings.luxmed_password:
                    cookie_header = refresh_auth_token(settings, state)
                    auth_key, auth_message = auth_token_status(cookie_header, settings.auth_expiry_warn_minutes)
                    telegram.send(f"<b>Luxmed auth refreshed</b>\n{html.escape(auth_message)}")
                    last_auth_warning_key = ""
                elif auth_key != last_auth_warning_key:
                    telegram.send(f"<b>Luxmed auth warning</b>\n{html.escape(auth_message)}")
                    last_auth_warning_key = auth_key

            last_status = process_telegram_commands(settings, state, telegram, auth_message, last_status)
            interval = active_poll_interval(settings, state)

            if auth_key.startswith(("missing", "invalid", "expired")):
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                last_status = f"Last check: {now}; skipped because auth is {auth_key.split(':', 1)[0]}"
                LOGGER.warning("%s; %s", last_status, auth_message)
                raise StopIteration

            results = check_all_jobs(settings, cookie_header)
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            last_status = format_live_status(now, results, interval, auth_key)
            LOGGER.info(last_status)

            if state_bool(state, "live_status_enabled"):
                telegram.send(format_live_status(now, results, interval, auth_key))

            for job, _total, matches in results:
                if not matches:
                    continue
                current_signature = signature(matches)
                if active_notify_on_every_match(settings, state) or current_signature != last_signatures.get(job.name):
                    telegram.send(format_match_message(matches, settings, job))
                    last_signatures[job.name] = current_signature
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else "?"
            last_status = f"HTTP error from Luxmed/Telegram: {status_code}. Session cookies may be expired."
            LOGGER.exception(last_status)
            if status_code in {401, 403}:
                warning_key = f"http-auth:{status_code}"
                if settings.luxmed_login and settings.luxmed_password:
                    cookie_header = refresh_auth_token(settings, state)
                    _, auth_message = auth_token_status(cookie_header, settings.auth_expiry_warn_minutes)
                    telegram.send(f"<b>Luxmed auth refreshed after HTTP {status_code}</b>\n{html.escape(auth_message)}")
                    last_http_auth_warning_key = ""
                elif warning_key != last_http_auth_warning_key:
                    telegram.send("Luxmed auth failed. Configure LUXMED_LOGIN/LUXMED_PASSWORD or refresh LUXMED_COOKIE_HEADER from browser.")
                    last_http_auth_warning_key = warning_key
        except StopIteration:
            pass
        except Exception:
            last_status = "Luxmed monitor error; check container logs."
            LOGGER.exception(last_status)

        interval = active_poll_interval(settings, state)
        second = 0
        while second < interval:
            if STOP:
                break
            if second % 2 == 0:
                try:
                    cookie_header = active_cookie_header(settings, state)
                    _auth_key, auth_message = auth_token_status(cookie_header, settings.auth_expiry_warn_minutes)
                    last_status = process_telegram_commands(settings, state, telegram, auth_message, last_status)
                    interval = active_poll_interval(settings, state)
                except Exception:
                    LOGGER.exception("Telegram command polling failed during wait.")
            time.sleep(1)
            second += 1

    telegram.send("Luxmed monitor stopped.")
    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    sys.exit(main())
