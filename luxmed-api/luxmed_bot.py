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


@dataclass
class LuxmedAccount:
    name: str
    login: str | None
    password: str | None
    cookie_header: str | None
    jobs: list[SearchJob]


def parse_job_items(data: Any, source: str) -> list[SearchJob]:
    if not isinstance(data, list):
        raise RuntimeError(f"{source} must be a JSON array.")

    jobs: list[SearchJob] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise RuntimeError(f"{source} item {index} must be an object.")
        request_url = str(item.get("request_url") or item.get("url") or "").strip()
        if not request_url:
            raise RuntimeError(f"{source} item {index} is missing request_url.")
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


def parse_jobs_from_env() -> list[SearchJob]:
    jobs_json = env("LUXMED_JOBS_JSON")
    if jobs_json:
        return parse_job_items(json.loads(jobs_json), "LUXMED_JOBS_JSON")

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


def derive_job_name(request_url: str) -> str:
    params = dict(parse_qsl(urlparse(request_url).query, keep_blank_values=True))
    service = params.get("serviceVariantId")
    date_from = params.get("searchDateFrom")
    if service and date_from:
        return f"service-{service}-{date_from}"
    if service:
        return f"service-{service}"
    return "runtime-job"


def parse_accounts_from_env() -> list[LuxmedAccount]:
    accounts_json = env("LUXMED_ACCOUNTS_JSON")
    if accounts_json:
        data = json.loads(accounts_json)
        if not isinstance(data, list):
            raise RuntimeError("LUXMED_ACCOUNTS_JSON must be a JSON array.")

        accounts: list[LuxmedAccount] = []
        for index, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                raise RuntimeError(f"LUXMED_ACCOUNTS_JSON item {index} must be an object.")
            jobs = parse_job_items(item.get("jobs"), f"LUXMED_ACCOUNTS_JSON account {index}.jobs")
            accounts.append(
                LuxmedAccount(
                    name=str(item.get("name") or item.get("login") or f"account-{index}"),
                    login=item.get("login") or None,
                    password=item.get("password") or None,
                    cookie_header=item.get("cookie_header") or None,
                    jobs=jobs,
                )
            )
        return accounts

    return [
        LuxmedAccount(
            name=env("LUXMED_ACCOUNT_NAME", "default") or "default",
            login=env("LUXMED_LOGIN") or None,
            password=env("LUXMED_PASSWORD") or None,
            cookie_header=env("LUXMED_COOKIE_HEADER") or None,
            jobs=parse_jobs_from_env(),
        )
    ]


@dataclass
class Settings:
    telegram_bot_token: str
    telegram_target_ids: list[str]
    luxmed_base_uri: str
    accounts: list[LuxmedAccount]
    poll_interval_seconds: int
    live_status_interval_seconds: int
    notify_on_every_match: bool
    request_timeout_seconds: int
    auth_expiry_warn_minutes: int
    rate_limit_backoff_seconds: int
    state_file: str

    @classmethod
    def from_env(cls) -> "Settings":
        telegram_target_ids = env_list("TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_IDS", "TELEGRAM_USER_IDS")
        if not telegram_target_ids:
            raise RuntimeError("Missing TELEGRAM_CHAT_ID, TELEGRAM_CHAT_IDS, or TELEGRAM_USER_IDS.")

        return cls(
            telegram_bot_token=env("TELEGRAM_BOT_TOKEN", required=True),
            telegram_target_ids=telegram_target_ids,
            luxmed_base_uri=env("LUXMED_BASE_URI", "https://portalpacjenta.luxmed.pl"),
            accounts=parse_accounts_from_env(),
            poll_interval_seconds=int(env("POLL_INTERVAL_SECONDS", "60")),
            live_status_interval_seconds=int(env("LIVE_STATUS_INTERVAL_SECONDS", "5")),
            notify_on_every_match=env_bool("NOTIFY_ON_EVERY_MATCH", False),
            request_timeout_seconds=int(env("REQUEST_TIMEOUT_SECONDS", "30")),
            auth_expiry_warn_minutes=int(env("AUTH_EXPIRY_WARN_MINUTES", "2")),
            rate_limit_backoff_seconds=int(env("RATE_LIMIT_BACKOFF_SECONDS", "300")),
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
        self.timeout_seconds = int(env("TELEGRAM_TIMEOUT_SECONDS", "20"))
        self.last_network_warning_at = 0.0

    def warn_network_issue(self, action: str, exc: Exception) -> None:
        now = time.time()
        if now - self.last_network_warning_at < 60:
            LOGGER.debug("Telegram %s transient network issue: %s", action, exc.__class__.__name__)
            return
        self.last_network_warning_at = now
        LOGGER.warning("Telegram %s transient network issue: %s", action, exc.__class__.__name__)

    def send(self, text: str, reply_markup: dict[str, Any] | None = None) -> dict[str, int]:
        message_ids: dict[str, int] = {}
        for target_id in self.target_ids:
            payload: dict[str, Any] = {
                "chat_id": target_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup
            try:
                response = requests.post(
                    f"{self.base_url}/sendMessage",
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            except requests.RequestException as exc:
                self.warn_network_issue("sendMessage", exc)
                continue
            if not response.ok:
                LOGGER.warning("Telegram sendMessage failed for %s: HTTP %s; %s", target_id, response.status_code, response.text[:500])
                continue
            result = response.json().get("result") or {}
            if isinstance(result, dict) and result.get("message_id") is not None:
                message_ids[target_id] = int(result["message_id"])
        return message_ids

    def edit(self, message_ids: dict[str, int], text: str, reply_markup: dict[str, Any] | None = None) -> dict[str, int]:
        active_message_ids: dict[str, int] = {}
        for target_id in self.target_ids:
            message_id = message_ids.get(target_id)
            if not message_id:
                continue
            payload: dict[str, Any] = {
                "chat_id": target_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup
            try:
                response = requests.post(
                    f"{self.base_url}/editMessageText",
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            except requests.RequestException as exc:
                self.warn_network_issue("editMessageText", exc)
                continue
            if response.ok:
                active_message_ids[target_id] = message_id
                continue
            LOGGER.warning("Telegram editMessageText failed for %s: HTTP %s; %s", target_id, response.status_code, response.text[:500])
        return active_message_ids

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> None:
        try:
            response = requests.post(
                f"{self.base_url}/answerCallbackQuery",
                json={"callback_query_id": callback_query_id, "text": text},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            self.warn_network_issue("answerCallbackQuery", exc)
            return
        if not response.ok:
            LOGGER.warning("Telegram answerCallbackQuery failed: HTTP %s; %s", response.status_code, response.text[:500])

    def set_my_commands(self) -> None:
        commands = [
            {"command": "menu", "description": "Show control buttons"},
            {"command": "status", "description": "Show last monitor status"},
            {"command": "check", "description": "Check all Luxmed jobs now"},
            {"command": "jobs", "description": "List configured Luxmed searches"},
            {"command": "add_job", "description": "Add Luxmed search URL to monitoring"},
            {"command": "remove_job", "description": "Remove runtime Luxmed search"},
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
        try:
            response = requests.post(
                f"{self.base_url}/setMyCommands",
                json={"commands": commands},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            self.warn_network_issue("setMyCommands", exc)
            return
        if not response.ok:
            LOGGER.warning("Telegram setMyCommands failed: HTTP %s; %s", response.status_code, response.text[:500])

    def poll_commands(self) -> list[str]:
        try:
            response = requests.get(
                f"{self.base_url}/getUpdates",
                params={"offset": self.offset, "timeout": 0, "allowed_updates": json.dumps(["message", "callback_query"])},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            self.warn_network_issue("getUpdates", exc)
            return []
        if not response.ok:
            if response.status_code >= 500 or response.status_code == 429:
                LOGGER.warning("Telegram getUpdates temporary failure: HTTP %s; %s", response.status_code, response.text[:500])
                return []
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


def login_luxmed(settings: Settings, account: LuxmedAccount, cookie_header: str) -> str:
    if not account.login or not account.password:
        raise RuntimeError(f"Luxmed login/password are required for automatic token refresh: {account.name}")

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
        json={"login": account.login, "password": account.password},
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


def normalize_term(term: dict[str, Any], day: dict[str, Any], service_id: Any, additional_data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "dateTimeFrom": term.get("dateTimeFrom"),
        "dateTimeTo": term.get("dateTimeTo"),
        "timeFrom": term.get("timeFrom") or time_value(term.get("dateTimeFrom")),
        "timeTo": term.get("timeTo") or time_value(term.get("dateTimeTo")),
        "doctor": term.get("doctor") if isinstance(term.get("doctor"), dict) else None,
        "doctorName": doctor_name(term),
        "doctorId": (term.get("doctor") or {}).get("id") if isinstance(term.get("doctor"), dict) else None,
        "clinic": term.get("clinic"),
        "clinicGroup": term.get("clinicGroup"),
        "clinicId": term.get("clinicId"),
        "facilityId": term.get("facilityId") or term.get("clinicId"),
        "roomId": term.get("roomId"),
        "serviceVariantId": service_id,
        "serviceId": term.get("serviceId") or service_id,
        "scheduleId": term.get("scheduleId"),
        "isTelemedicine": term.get("isTelemedicine"),
        "isAdditional": term.get("isAdditional"),
        "isImpediment": term.get("isImpediment"),
        "impedimentText": term.get("impedimentText"),
        "eReferralId": term.get("eReferralId"),
        "parentReservationId": term.get("parentReservationId"),
        "referralId": term.get("referralId"),
        "referralTypeId": term.get("referralTypeId"),
        "isPreparationRequired": term.get("isPreparationRequired"),
        "preparationItems": term.get("preparationItems"),
        "additionalData": additional_data or {},
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
            additional_data = service.get("additionalData") if isinstance(service.get("additionalData"), dict) else {}
            normalized: list[dict[str, Any]] = []
            for day in service.get("termsForDays") or []:
                if not isinstance(day, dict):
                    continue
                for term in day.get("terms") or []:
                    if isinstance(term, dict):
                        normalized.append(normalize_term(term, day, service_id, additional_data))
            return normalized

        terms = payload.get("terms")
        if isinstance(terms, list):
            return [normalize_term(term, {}, None) for term in terms if isinstance(term, dict)]

    if isinstance(payload, list):
        return [normalize_term(term, {}, None) for term in payload if isinstance(term, dict)]

    return []


def reservation_lockterm_payload(job: SearchJob, term: dict[str, Any]) -> dict[str, Any]:
    params = request_params(job)
    additional_data = term.get("additionalData") if isinstance(term.get("additionalData"), dict) else {}
    preparation_items = term.get("preparationItems")
    if preparation_items is None:
        preparation_items = additional_data.get("preparationItems") if isinstance(additional_data, dict) else None

    return {
        "date": term.get("dateTimeFrom") or term.get("day"),
        "doctor": term.get("doctor") or {},
        "doctorId": term.get("doctorId"),
        "eReferralId": term.get("eReferralId"),
        "facilityId": term.get("facilityId") or term.get("clinicId"),
        "impedimentText": term.get("impedimentText"),
        "isAdditional": bool(term.get("isAdditional")),
        "isImpediment": bool(term.get("isImpediment")),
        "isPreparationRequired": bool(term.get("isPreparationRequired") or additional_data.get("isPreparationRequired")),
        "isTelemedicine": bool(term.get("isTelemedicine")),
        "parentReservationId": term.get("parentReservationId"),
        "preparationItems": preparation_items or [],
        "referralId": term.get("referralId") or params.get("referralId"),
        "referralTypeId": term.get("referralTypeId") or params.get("referralTypeId"),
        "roomId": term.get("roomId"),
        "scheduleId": term.get("scheduleId"),
        "serviceVariantId": term.get("serviceVariantId") or params.get("serviceVariantId"),
        "timeFrom": term.get("timeFrom"),
        "timeTo": term.get("timeTo"),
    }


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

    header = (
        "<b>Luxmed: found appointment windows</b>\n"
        f"Job: <code>{html.escape(job.name)}</code>\n"
        f"ServiceVariantId: <code>{html.escape(service)}</code>\n"
        f"ReferralId: <code>{html.escape(referral_id)}</code>\n"
        f"ProcessId: <code>{html.escape(process_id)}</code>\n"
        f"Dates: <code>{html.escape(date_from)}</code> - <code>{html.escape(date_to)}</code>\n"
        f"Matches: <code>{len(matches)}</code>\n\n"
    )
    footer = (
        f"\n\n<a href=\"{html.escape(results_page_url(settings))}\">Open Luxmed results page</a>\n"
        f"<a href=\"{html.escape(job.request_url)}\">Open API request</a>"
    )
    max_preview_length = max(500, 3900 - len(header) - len(footer))

    preview_parts: list[str] = []
    current_length = 0
    shown = 0
    for term in matches:
        formatted = format_term(term, settings, job)
        separator = "\n\n" if preview_parts else ""
        next_length = current_length + len(separator) + len(formatted)
        if next_length > max_preview_length:
            break
        preview_parts.append(formatted)
        current_length = next_length
        shown += 1

    if shown < len(matches):
        suffix = f"\n\n...and {len(matches) - shown} more"
        if current_length + len(suffix) <= max_preview_length:
            preview_parts.append(suffix.strip())

    preview = "\n\n".join(preview_parts) if preview_parts else "Too many matching slots to fit in one Telegram message."
    return f"{header}{preview}{footer}"


def run_once(settings: Settings, job: SearchJob, cookie_header: str) -> tuple[int, list[dict[str, Any]]]:
    payload, raw_text = fetch_luxmed(settings, job, cookie_header)
    terms = extract_terms(payload, raw_text)
    matches = matches_filters(terms, raw_text, job)
    return len(terms), matches


def account_state_key(account: LuxmedAccount, key: str) -> str:
    if account.name == "default":
        return key
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", account.name).strip("_") or "account"
    return f"account.{safe_name}.{key}"


def active_cookie_header(state: StateStore, account: LuxmedAccount) -> str:
    return state.get(account_state_key(account, "luxmed_cookie_header"), account.cookie_header or "")


def refresh_auth_token(settings: Settings, state: StateStore, account: LuxmedAccount) -> str:
    cookie_header = active_cookie_header(state, account)
    token = login_luxmed(settings, account, cookie_header)
    cookie_header = upsert_cookie(cookie_header, "Authorization-Token", token)
    state.set(account_state_key(account, "luxmed_cookie_header"), cookie_header)
    return cookie_header


def runtime_jobs_key(account: LuxmedAccount) -> str:
    return account_state_key(account, "runtime_jobs_json")


def runtime_jobs(state: StateStore, account: LuxmedAccount) -> list[SearchJob]:
    raw = state.get(runtime_jobs_key(account), "[]")
    try:
        return parse_job_items(json.loads(raw), runtime_jobs_key(account))
    except Exception:
        LOGGER.exception("Invalid runtime jobs state for account %s.", account.name)
        return []


def account_jobs(state: StateStore | None, account: LuxmedAccount) -> list[SearchJob]:
    if state is None:
        return account.jobs
    return account.jobs + runtime_jobs(state, account)


def add_runtime_job(state: StateStore, account: LuxmedAccount, job: SearchJob) -> tuple[bool, str]:
    existing = account_jobs(state, account)
    for current in existing:
        if current.request_url == job.request_url:
            return False, current.name

    stored = [
        {
            "name": current.name,
            "request_url": current.request_url,
            "doctor_regex": current.doctor_regex,
            "clinic_regex": current.clinic_regex,
            "time_from": current.time_from,
            "time_to": current.time_to,
            "match_text_regex": current.match_text_regex,
        }
        for current in runtime_jobs(state, account)
    ]
    stored.append(
        {
            "name": job.name,
            "request_url": job.request_url,
            "doctor_regex": job.doctor_regex,
            "clinic_regex": job.clinic_regex,
            "time_from": job.time_from,
            "time_to": job.time_to,
            "match_text_regex": job.match_text_regex,
        }
    )
    state.set(runtime_jobs_key(account), json.dumps(stored, ensure_ascii=False))
    return True, job.name


def job_to_state_item(job: SearchJob) -> dict[str, str | None]:
    return {
        "name": job.name,
        "request_url": job.request_url,
        "doctor_regex": job.doctor_regex,
        "clinic_regex": job.clinic_regex,
        "time_from": job.time_from,
        "time_to": job.time_to,
        "match_text_regex": job.match_text_regex,
    }


def remove_runtime_job(state: StateStore, account: LuxmedAccount, selector: str) -> tuple[bool, str]:
    selector = selector.strip()
    if not selector:
        return False, "Usage: /remove_job [account] <runtime job name or URL>"

    runtime = runtime_jobs(state, account)
    remaining: list[SearchJob] = []
    removed: SearchJob | None = None
    for job in runtime:
        if removed is None and (job.name == selector or job.request_url == selector):
            removed = job
            continue
        remaining.append(job)

    if removed:
        state.set(runtime_jobs_key(account), json.dumps([job_to_state_item(job) for job in remaining], ensure_ascii=False))
        return True, removed.name

    for job in account.jobs:
        if job.name == selector or job.request_url == selector:
            return False, f"<code>{html.escape(job.name)}</code> comes from .env; edit LUXMED_JOBS_JSON/LUXMED_REQUEST_URL to remove it."

    return False, f"No runtime job matched <code>{html.escape(selector)}</code> for account <code>{html.escape(account.name)}</code>."


def parse_add_job_argument(settings: Settings, argument: str) -> tuple[LuxmedAccount, SearchJob] | None:
    match = re.search(r"https?://\S+", argument)
    if not match:
        return None

    request_url = match.group(0).strip()
    prefix = argument[: match.start()].strip()
    account, name = resolve_account_argument(settings, prefix)
    job_name = name or derive_job_name(request_url)
    return account, SearchJob(name=job_name, request_url=request_url)


def parse_remove_job_argument(settings: Settings, argument: str) -> tuple[LuxmedAccount, str]:
    account, selector = resolve_account_argument(settings, argument)
    return account, selector


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
                {"text": "Live 5s", "callback_data": "/live 5"},
                {"text": "Live 1m", "callback_data": "/live 60"},
            ],
            [
                {"text": "Live off", "callback_data": "/live_off"},
                {"text": "Notify once", "callback_data": "/notify_once"},
            ],
            [
                {"text": "Notify every", "callback_data": "/notify_every"},
                {"text": "Refresh auth", "callback_data": "/login"},
            ],
            [
                {"text": "Menu", "callback_data": "/menu"},
            ],
        ]
    }


def help_text(settings: Settings) -> str:
    account_names = ", ".join(account.name for account in settings.accounts) or "default"
    first_account = settings.accounts[0].name if settings.accounts else "default"
    return (
        "<b>Luxmed monitor controls</b>\n"
        f"Configured accounts: <code>{html.escape(account_names)}</code>\n\n"
        "/status - show the latest monitor status.\n"
        "Example: <code>/status</code>\n\n"
        "/check - run all tracked searches now.\n"
        "Example: <code>/check</code>\n\n"
        "/jobs - list configured and runtime appointment searches.\n"
        "Example: <code>/jobs</code>\n\n"
        "/add_job [account] [name] &lt;Luxmed terms/index URL&gt; - add a runtime search saved in STATE_FILE.\n"
        f"Example default account: <code>/add_job Dermatology https://portalpacjenta.luxmed.pl/PatientPortal/NewPortal/terms/index?...</code>\n"
        f"Example named account: <code>/add_job {html.escape(first_account)} Dermatology https://portalpacjenta.luxmed.pl/PatientPortal/NewPortal/terms/index?...</code>\n"
        "[account]: optional account name from the configured accounts. [name]: human-readable search name. URL: captured Luxmed terms/index request.\n\n"
        "/remove_job [account] &lt;runtime job name or URL&gt; - remove a runtime search from STATE_FILE.\n"
        "Example default account: <code>/remove_job Dermatology</code>\n"
        f"Example named account: <code>/remove_job {html.escape(first_account)} Dermatology</code>\n"
        "[account]: optional account name. Selector: exact runtime job name or exact captured URL. .env jobs cannot be removed here.\n\n"
        "/config - show current bot config.\n"
        "Example: <code>/config</code>\n\n"
        "/interval &lt;seconds&gt; - set background poll interval.\n"
        "Example: <code>/interval 3600</code>. seconds: minimum 10.\n\n"
        "/live [seconds] - enable one editable live status message.\n"
        "Example: <code>/live 5</code>. seconds: optional live refresh interval, minimum 5.\n\n"
        "/live_off - disable live status updates.\n"
        "Example: <code>/live_off</code>\n\n"
        "/notify_once - notify only when matching results change.\n"
        "Example: <code>/notify_once</code>\n\n"
        "/notify_every - notify on every check with matching results.\n"
        "Example: <code>/notify_every</code>\n\n"
        "/login [account] - refresh Luxmed auth token.\n"
        f"Example: <code>/login {html.escape(first_account)}</code>. [account]: optional account name."
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


def active_live_interval(settings: Settings, state: StateStore) -> int:
    raw = state.get("live_status_interval_seconds", str(settings.live_status_interval_seconds))
    try:
        return max(5, int(raw))
    except ValueError:
        return max(5, settings.live_status_interval_seconds)


def active_check_interval(settings: Settings, state: StateStore) -> int:
    if state_bool(state, "live_status_enabled"):
        return active_live_interval(settings, state)
    return active_poll_interval(settings, state)


def active_display_interval(poll_interval: int, live_interval: int, live_enabled: bool) -> int:
    return live_interval if live_enabled else poll_interval


def active_notify_on_every_match(settings: Settings, state: StateStore) -> bool:
    raw = state.get("notify_on_every_match", "true" if settings.notify_on_every_match else "false")
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def set_poll_interval(state: StateStore, seconds: int) -> None:
    state.set("poll_interval_seconds", str(max(10, seconds)))


def set_live_interval(state: StateStore, seconds: int) -> None:
    state.set("live_status_interval_seconds", str(max(5, seconds)))


def total_job_count(settings: Settings, state: StateStore | None = None) -> int:
    return sum(len(account_jobs(state, account)) for account in settings.accounts)


def format_jobs(settings: Settings, state: StateStore | None = None) -> str:
    lines = ["Luxmed jobs:"]
    index = 1
    for account in settings.accounts:
        for job in account_jobs(state, account):
            params = request_params(job)
            lines.append(
                "\n"
                f"{index}. <b>{html.escape(account.name)} / {html.escape(job.name)}</b>\n"
                f"serviceVariantId=<code>{html.escape(params.get('serviceVariantId', '?'))}</code>; "
                f"referralId=<code>{html.escape(params.get('referralId', '?'))}</code>\n"
                f"doctor=<code>{html.escape(job.doctor_regex or '-')}</code>; "
                f"clinic=<code>{html.escape(job.clinic_regex or '-')}</code>; "
                f"time=<code>{html.escape(job.time_from or '-')}</code>-<code>{html.escape(job.time_to or '-')}</code>\n"
                f"<a href=\"{html.escape(results_page_url(settings))}\">Open Luxmed result</a> | "
                f"<a href=\"{html.escape(job.request_url)}\">Open API request</a>"
            )
            index += 1
    return "\n".join(lines)


CheckResult = tuple[LuxmedAccount, SearchJob, int, list[dict[str, Any]]]


def check_account_jobs(settings: Settings, state: StateStore, account: LuxmedAccount, cookie_header: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    for job in account_jobs(state, account):
        total, matches = run_once(settings, job, cookie_header)
        results.append((account, job, total, matches))
    return results


def check_all_accounts(settings: Settings, state: StateStore, auth_keys: dict[str, str] | None = None) -> list[CheckResult]:
    results: list[CheckResult] = []
    for account in settings.accounts:
        auth_key = (auth_keys or {}).get(account.name, "")
        if auth_key.startswith(("missing", "invalid", "expired")):
            results.extend((account, job, 0, []) for job in account_jobs(state, account))
            continue
        cookie_header = active_cookie_header(state, account)
        results.extend(check_account_jobs(settings, state, account, cookie_header))
    return results


def format_live_status(
    settings: Settings,
    checked_at: str,
    results: list[CheckResult],
    poll_interval: int,
    live_interval: int,
    live_enabled: bool,
    auth_keys: dict[str, str],
) -> str:
    lines = [
        "<b>Luxmed live status</b>",
        f"Checked: <code>{html.escape(checked_at)}</code>",
        f"Next check: <code>{active_display_interval(poll_interval, live_interval, live_enabled)}s</code>",
        f"Poll interval: <code>{poll_interval}s</code>",
        f"Live refresh: <code>{'on' if live_enabled else 'off'}{f' / {live_interval}s' if live_enabled else ''}</code>",
        "",
    ]
    for account, job, total, matches in results:
        auth = auth_keys.get(account.name, "unknown").split(":", 1)[0]
        lines.append(
            f"<b>{html.escape(account.name)} / {html.escape(job.name)}</b>: "
            f"terms=<code>{total}</code>, matches=<code>{len(matches)}</code>, auth=<code>{html.escape(auth)}</code>"
        )
        if matches:
            for term in matches[:3]:
                if term.get("rawText"):
                    lines.append(f"- {html.escape(str(term['rawText'])[:240])}")
                    continue
                when = term.get("dateTimeFrom") or "?"
                doctor = term.get("doctorName") or "Unknown doctor"
                clinic = term.get("clinic") or term.get("clinicGroup") or "Unknown clinic"
                slot_url = term_reference_url(term, settings, job)
                lines.append(
                    f"- <a href=\"{html.escape(slot_url)}\">{html.escape(str(when))}</a> "
                    f"{html.escape(str(doctor))}, {html.escape(str(clinic))}"
                )
            if len(matches) > 3:
                lines.append(f"- ...and <code>{len(matches) - 3}</code> more")
    return "\n".join(lines)


def resolve_account_argument(settings: Settings, argument: str) -> tuple[LuxmedAccount, str]:
    if not settings.accounts:
        raise RuntimeError("No Luxmed accounts configured.")
    if not argument:
        return settings.accounts[0], ""

    normalized = argument.lower()
    for account in sorted(settings.accounts, key=lambda item: len(item.name), reverse=True):
        account_name = account.name.lower()
        if normalized == account_name:
            return account, ""
        if normalized.startswith(f"{account_name} "):
            return account, argument[len(account.name) :].strip()
    return settings.accounts[0], argument


def auth_status_by_account(settings: Settings, state: StateStore) -> tuple[dict[str, str], str]:
    keys: dict[str, str] = {}
    messages: list[str] = []
    for account in settings.accounts:
        key, message = auth_token_status(active_cookie_header(state, account), settings.auth_expiry_warn_minutes)
        keys[account.name] = key
        messages.append(f"<b>{html.escape(account.name)}</b>: {html.escape(message)}")
    return keys, "\n".join(messages)


def refresh_expiring_auth(settings: Settings, state: StateStore, telegram: Telegram, last_warning_keys: dict[str, str]) -> dict[str, str]:
    auth_keys: dict[str, str] = {}
    for account in settings.accounts:
        cookie_header = active_cookie_header(state, account)
        auth_key, auth_message = auth_token_status(cookie_header, settings.auth_expiry_warn_minutes)
        if auth_key.startswith(("missing", "invalid", "expired", "expiring")):
            if account.login and account.password:
                cookie_header = refresh_auth_token(settings, state, account)
                auth_key, auth_message = auth_token_status(cookie_header, settings.auth_expiry_warn_minutes)
                telegram.send(f"<b>Luxmed auth refreshed</b>\nAccount: <code>{html.escape(account.name)}</code>\n{html.escape(auth_message)}")
                last_warning_keys[account.name] = ""
            elif auth_key != last_warning_keys.get(account.name):
                telegram.send(
                    f"<b>Luxmed auth warning</b>\n"
                    f"Account: <code>{html.escape(account.name)}</code>\n"
                    f"{html.escape(auth_message)}"
                )
                last_warning_keys[account.name] = auth_key
        auth_keys[account.name] = auth_key
    return auth_keys


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
        telegram.send(help_text(settings), reply_markup=main_menu_markup())
    elif command == "/auth":
        telegram.send(auth_message)
    elif command == "/status":
        telegram.send(last_status)
    elif command == "/jobs":
        telegram.send(format_jobs(settings, state))
    elif command in {"/add_job", "/add_appointment", "/track"}:
        parsed = parse_add_job_argument(settings, argument)
        if not parsed:
            telegram.send("Usage: /add_job [account] [name] <Luxmed terms/index URL>")
            return None
        account, job = parsed
        added, name = add_runtime_job(state, account, job)
        if added:
            telegram.send(
                "Luxmed appointment search added.\n"
                f"Account: <code>{html.escape(account.name)}</code>\n"
                f"Job: <code>{html.escape(name)}</code>\n"
                f"Total jobs: <code>{total_job_count(settings, state)}</code>",
                reply_markup=main_menu_markup(),
            )
        else:
            telegram.send(
                "This Luxmed appointment search is already tracked.\n"
                f"Account: <code>{html.escape(account.name)}</code>\n"
                f"Job: <code>{html.escape(name)}</code>"
            )
    elif command in {"/remove_job", "/delete_job", "/untrack"}:
        account, selector = parse_remove_job_argument(settings, argument)
        removed, message = remove_runtime_job(state, account, selector)
        if removed:
            telegram.send(
                "Luxmed runtime appointment search removed.\n"
                f"Account: <code>{html.escape(account.name)}</code>\n"
                f"Job: <code>{html.escape(message)}</code>\n"
                f"Total jobs: <code>{total_job_count(settings, state)}</code>",
                reply_markup=main_menu_markup(),
            )
        else:
            telegram.send(message)
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
            set_live_interval(state, int(argument))
        state.set("live_status_enabled", "true")
        telegram.send(f"Live status enabled. Refresh: <code>{active_live_interval(settings, state)}s</code>.")
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
            f"Poll interval: <code>{active_poll_interval(settings, state)}s</code>\n"
            f"Live refresh: <code>{active_live_interval(settings, state)}s</code>\n"
            f"Auth expiry warning: <code>{settings.auth_expiry_warn_minutes}m</code>\n"
            f"Accounts: <code>{len(settings.accounts)}</code>\n"
            f"Accounts with auto login: <code>{sum(1 for account in settings.accounts if account.login and account.password)}</code>\n"
            f"Jobs: <code>{total_job_count(settings, state)}</code>\n"
            f"Live status: <code>{'on' if state_bool(state, 'live_status_enabled') else 'off'}</code>\n"
            f"Notify every match: <code>{'on' if active_notify_on_every_match(settings, state) else 'off'}</code>\n"
            f"State file: <code>{html.escape(settings.state_file)}</code>"
        )
    elif command == "/menu":
        telegram.send("Luxmed monitor menu", reply_markup=main_menu_markup())
    elif command == "/set_cookie":
        account, value = resolve_account_argument(settings, argument)
        if not value:
            telegram.send("Usage: /set_cookie [account] Authorization-Token=...; XSRF-TOKEN=...")
            return
        state.set(account_state_key(account, "luxmed_cookie_header"), value)
        telegram.send(f"Luxmed cookie header updated for <code>{html.escape(account.name)}</code>.")
    elif command in {"/set_auth", "/set_token"}:
        account, value = resolve_account_argument(settings, argument)
        if not value:
            telegram.send("Usage: /set_auth [account] <Authorization-Token>")
            return
        cookie_header = upsert_cookie(active_cookie_header(state, account), "Authorization-Token", value)
        state.set(account_state_key(account, "luxmed_cookie_header"), cookie_header)
        telegram.send(f"Luxmed Authorization-Token updated for <code>{html.escape(account.name)}</code>.")
    elif command == "/set_xsrf":
        account, value = resolve_account_argument(settings, argument)
        if not value:
            telegram.send("Usage: /set_xsrf [account] <XSRF-TOKEN>")
            return
        cookie_header = upsert_cookie(active_cookie_header(state, account), "XSRF-TOKEN", value)
        state.set(account_state_key(account, "luxmed_cookie_header"), cookie_header)
        telegram.send(f"Luxmed XSRF-TOKEN updated for <code>{html.escape(account.name)}</code>.")
    elif command == "/set_refresh":
        account, value = resolve_account_argument(settings, argument)
        if not value:
            telegram.send("Usage: /set_refresh [account] <RefreshToken>")
            return
        cookie_header = upsert_cookie(active_cookie_header(state, account), "RefreshToken", value)
        state.set(account_state_key(account, "luxmed_cookie_header"), cookie_header)
        telegram.send(f"Luxmed RefreshToken updated for <code>{html.escape(account.name)}</code>.")
    elif command == "/set_lx":
        account, value = resolve_account_argument(settings, argument)
        if not value:
            telegram.send("Usage: /set_lx [account] <LXToken>")
            return
        cookie_header = upsert_cookie(active_cookie_header(state, account), "LXToken", value)
        state.set(account_state_key(account, "luxmed_cookie_header"), cookie_header)
        telegram.send(f"Luxmed LXToken updated for <code>{html.escape(account.name)}</code>.")
    elif command == "/login":
        account, _value = resolve_account_argument(settings, argument)
        cookie_header = refresh_auth_token(settings, state, account)
        _, auth_message = auth_token_status(cookie_header, settings.auth_expiry_warn_minutes)
        telegram.send(f"Luxmed token refreshed for <code>{html.escape(account.name)}</code>.\n{html.escape(auth_message)}")

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
            try:
                auth_keys, _auth_message = auth_status_by_account(settings, state)
                results = check_all_accounts(settings, state, auth_keys)
                checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                last_status = format_live_status(
                    settings,
                    checked_at,
                    results,
                    active_poll_interval(settings, state),
                    active_live_interval(settings, state),
                    state_bool(state, "live_status_enabled"),
                    auth_keys,
                )
                sent_match = False
                for _account, job, _total, matches in results:
                    if matches:
                        telegram.send(format_match_message(matches, settings, job))
                        sent_match = True
                if not sent_match:
                    summary = ", ".join(f"{account.name}/{job.name}: terms={total}, matches=0" for account, job, total, _ in results)
                    telegram.send(f"Manual check: no matching appointment windows right now.\n{html.escape(summary)}")
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else "?"
                if status_code == 429:
                    telegram.send(
                        "Manual check failed: Luxmed returned <code>HTTP 429</code> rate limit.\n"
                        f"The bot will back off for <code>{settings.rate_limit_backoff_seconds}s</code>."
                    )
                else:
                    telegram.send(f"Manual check failed: Luxmed returned <code>HTTP {status_code}</code>. Check container logs for details.")
                LOGGER.exception("Manual Luxmed check failed.")
            except Exception:
                telegram.send("Manual check failed. Check container logs for details.")
                LOGGER.exception("Manual Luxmed check failed.")
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
    last_auth_warning_keys: dict[str, str] = {}
    last_http_auth_warning_keys: dict[str, str] = {}
    live_message_ids: dict[str, int] = {}
    rate_limited_until = 0.0

    telegram.set_my_commands()
    telegram.send(
        f"Luxmed monitor started. Accounts: <code>{len(settings.accounts)}</code>, jobs: <code>{total_job_count(settings, state)}</code>.",
        reply_markup=main_menu_markup(),
    )

    while not STOP:
        interval = active_check_interval(settings, state)
        try:
            auth_keys = refresh_expiring_auth(settings, state, telegram, last_auth_warning_keys)
            _auth_keys, auth_message = auth_status_by_account(settings, state)

            last_status = process_telegram_commands(settings, state, telegram, auth_message, last_status)
            interval = active_check_interval(settings, state)
            auth_keys, auth_message = auth_status_by_account(settings, state)

            blocked_accounts = [
                f"{account.name}={auth_keys.get(account.name, 'unknown').split(':', 1)[0]}"
                for account in settings.accounts
                if auth_keys.get(account.name, "").startswith(("missing", "invalid", "expired"))
            ]
            if blocked_accounts:
                LOGGER.warning("Some Luxmed accounts are not authenticated: %s", ", ".join(blocked_accounts))

            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if time.time() < rate_limited_until:
                retry_at = datetime.fromtimestamp(rate_limited_until, tz=timezone.utc).isoformat(timespec="seconds")
                last_status = (
                    "<b>Luxmed live status</b>\n"
                    f"Checked: <code>{html.escape(now)}</code>\n"
                    f"Next check: <code>{active_check_interval(settings, state)}s</code>\n"
                    f"Luxmed rate limit: <code>HTTP 429</code>\n"
                    f"Retry after: <code>{html.escape(retry_at)}</code>"
                )
                results = []
            else:
                results = check_all_accounts(settings, state, auth_keys)
                last_status = format_live_status(
                    settings,
                    now,
                    results,
                    active_poll_interval(settings, state),
                    active_live_interval(settings, state),
                    state_bool(state, "live_status_enabled"),
                    auth_keys,
                )
            LOGGER.info(last_status)

            if state_bool(state, "live_status_enabled"):
                live_message_ids = telegram.edit(live_message_ids, last_status, reply_markup=main_menu_markup())
                if len(live_message_ids) < len(telegram.target_ids):
                    live_message_ids.update(telegram.send(last_status, reply_markup=main_menu_markup()))
            else:
                live_message_ids = {}

            for account, job, _total, matches in results:
                if not matches:
                    continue
                current_signature = signature(matches)
                signature_key = f"{account.name}/{job.name}"
                if active_notify_on_every_match(settings, state) or current_signature != last_signatures.get(signature_key):
                    telegram.send(format_match_message(matches, settings, job))
                    last_signatures[signature_key] = current_signature
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else "?"
            last_status = f"HTTP error from Luxmed/Telegram: {status_code}. Session cookies may be expired."
            LOGGER.exception(last_status)
            if status_code == 429:
                rate_limited_until = time.time() + settings.rate_limit_backoff_seconds
                retry_at = datetime.fromtimestamp(rate_limited_until, tz=timezone.utc).isoformat(timespec="seconds")
                last_status = (
                    "<b>Luxmed live status</b>\n"
                    f"Luxmed rate limit: <code>HTTP 429</code>\n"
                    f"Retry after: <code>{html.escape(retry_at)}</code>\n"
                    f"Backoff: <code>{settings.rate_limit_backoff_seconds}s</code>"
                )
                if state_bool(state, "live_status_enabled"):
                    live_message_ids = telegram.edit(live_message_ids, last_status, reply_markup=main_menu_markup())
                    if len(live_message_ids) < len(telegram.target_ids):
                        live_message_ids.update(telegram.send(last_status, reply_markup=main_menu_markup()))
            if status_code in {401, 403}:
                warning_key = f"http-auth:{status_code}"
                for account in settings.accounts:
                    if account.login and account.password:
                        cookie_header = refresh_auth_token(settings, state, account)
                        _, auth_message = auth_token_status(cookie_header, settings.auth_expiry_warn_minutes)
                        telegram.send(
                            f"<b>Luxmed auth refreshed after HTTP {status_code}</b>\n"
                            f"Account: <code>{html.escape(account.name)}</code>\n"
                            f"{html.escape(auth_message)}"
                        )
                        last_http_auth_warning_keys[account.name] = ""
                    elif warning_key != last_http_auth_warning_keys.get(account.name):
                        telegram.send(
                            f"Luxmed auth failed for <code>{html.escape(account.name)}</code>. "
                            "Configure login/password or refresh the cookie header from browser."
                        )
                        last_http_auth_warning_keys[account.name] = warning_key
        except StopIteration:
            pass
        except Exception:
            last_status = "Luxmed monitor error; check container logs."
            LOGGER.exception(last_status)

        interval = active_check_interval(settings, state)
        second = 0
        while second < interval:
            if STOP:
                break
            if second % 2 == 0:
                try:
                    _auth_keys, auth_message = auth_status_by_account(settings, state)
                    last_status = process_telegram_commands(settings, state, telegram, auth_message, last_status)
                    interval = active_check_interval(settings, state)
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
