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
from urllib.parse import urlparse

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


@dataclass
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str
    luxmed_request_url: str
    luxmed_cookie_header: str
    doctor_regex: str | None
    match_text_regex: str | None
    poll_interval_seconds: int
    notify_on_every_match: bool
    request_timeout_seconds: int
    auth_expiry_warn_minutes: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            telegram_bot_token=env("TELEGRAM_BOT_TOKEN", required=True),
            telegram_chat_id=env("TELEGRAM_CHAT_ID", required=True),
            luxmed_request_url=env("LUXMED_REQUEST_URL", required=True),
            luxmed_cookie_header=env("LUXMED_COOKIE_HEADER", required=True),
            doctor_regex=env("LUXMED_DOCTOR_REGEX") or None,
            match_text_regex=env("LUXMED_MATCH_TEXT_REGEX") or None,
            poll_interval_seconds=int(env("POLL_INTERVAL_SECONDS", "60")),
            notify_on_every_match=env_bool("NOTIFY_ON_EVERY_MATCH", False),
            request_timeout_seconds=int(env("REQUEST_TIMEOUT_SECONDS", "30")),
            auth_expiry_warn_minutes=int(env("AUTH_EXPIRY_WARN_MINUTES", "2")),
        )


class Telegram:
    def __init__(self, token: str, chat_id: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.chat_id = chat_id
        self.offset = 0

    def send(self, text: str) -> None:
        response = requests.post(
            f"{self.base_url}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        response.raise_for_status()

    def poll_commands(self) -> list[str]:
        response = requests.get(
            f"{self.base_url}/getUpdates",
            params={"offset": self.offset, "timeout": 0, "allowed_updates": json.dumps(["message"])},
            timeout=20,
        )
        response.raise_for_status()

        commands: list[str] = []
        for update in response.json().get("result", []):
            self.offset = max(self.offset, update["update_id"] + 1)
            message = update.get("message") or {}
            if str(message.get("chat", {}).get("id")) != str(self.chat_id):
                continue
            text = (message.get("text") or "").strip()
            if text.startswith("/"):
                commands.append(text.split()[0].lower())
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


def decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("Authorization-Token is not a JWT")

    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
    return json.loads(decoded)


def auth_token_status(settings: Settings) -> tuple[str, str]:
    cookies = cookie_dict(settings.luxmed_cookie_header)
    token = cookies.get("Authorization-Token")
    if not token:
        return "missing", "Authorization-Token is missing from LUXMED_COOKIE_HEADER. Refresh/copy cookies from browser."

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

    warn_seconds = settings.auth_expiry_warn_minutes * 60
    if seconds_left <= warn_seconds:
        return (
            f"expiring:{exp}",
            f"Luxmed Authorization-Token expires soon: {expires_text} ({seconds_left}s left). Refresh .env from browser.",
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
        "Cookie": cookie_header,
        "Pragma": "no-cache",
        "Referer": f"{origin}/PatientPortal/NewPortal/Page/Reservation/Results",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
    }
    xsrf = cookies.get("XSRF-TOKEN")
    if xsrf:
        headers["X-XSRF-TOKEN"] = xsrf
        headers["xsrf-token"] = xsrf
    return headers


def fetch_luxmed(settings: Settings) -> tuple[Any, str]:
    response = requests.get(
        settings.luxmed_request_url,
        headers=luxmed_headers(settings.luxmed_request_url, settings.luxmed_cookie_header),
        timeout=settings.request_timeout_seconds,
    )
    response.raise_for_status()

    text = response.text
    try:
        return response.json(), text
    except ValueError:
        return None, text


def walk(value: Any) -> list[Any]:
    items = [value]
    if isinstance(value, dict):
        for nested in value.values():
            items.extend(walk(nested))
    elif isinstance(value, list):
        for nested in value:
            items.extend(walk(nested))
    return items


def flatten_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def looks_like_term(value: Any) -> bool:
    if not isinstance(value, dict):
        return False

    keys = {str(key).lower() for key in value.keys()}
    has_time = any("date" in key or "time" in key or "hour" in key or "term" in key for key in keys)
    has_person_or_place = any(
        "doctor" in key
        or "physician" in key
        or "specialist" in key
        or "resource" in key
        or "clinic" in key
        or "room" in key
        or "address" in key
        for key in keys
    )
    return has_time and has_person_or_place


def extract_terms(payload: Any, raw_text: str) -> list[str]:
    if payload is None:
        stripped = re.sub(r"<[^>]+>", " ", raw_text)
        stripped = re.sub(r"\s+", " ", stripped).strip()
        return [stripped[:1200]] if stripped else []

    terms = [flatten_text(item) for item in walk(payload) if looks_like_term(item)]
    if terms:
        return terms

    if isinstance(payload, list) and payload:
        return [flatten_text(item) for item in payload[:20]]

    if isinstance(payload, dict):
        for key in ("terms", "items", "data", "results", "availableTerms"):
            value = payload.get(key)
            if isinstance(value, list) and value:
                return [flatten_text(item) for item in value[:20]]

    return []


def matches_filters(terms: list[str], raw_text: str, settings: Settings) -> list[str]:
    candidates = terms or []

    if settings.doctor_regex:
        pattern = re.compile(settings.doctor_regex, re.IGNORECASE)
        candidates = [term for term in candidates if pattern.search(term)]

    if settings.match_text_regex:
        pattern = re.compile(settings.match_text_regex, re.IGNORECASE)
        if candidates:
            candidates = [term for term in candidates if pattern.search(term)]
        elif pattern.search(raw_text):
            candidates = [raw_text[:1200]]

    return candidates


def signature(matches: list[str]) -> str:
    normalized = "\n".join(sorted(matches))
    return str(hash(normalized))


def format_match_message(matches: list[str], settings: Settings) -> str:
    params = dict(re.findall(r"[?&]([^=&]+)=([^&]*)", settings.luxmed_request_url))
    service = params.get("serviceVariantId", "?")
    date_from = params.get("searchDateFrom", "?")
    date_to = params.get("searchDateTo", "?")

    preview = "\n\n".join(matches[:5])
    if len(matches) > 5:
        preview += f"\n\n...and {len(matches) - 5} more"

    return (
        "<b>Luxmed: found matching appointment terms</b>\n"
        f"ServiceVariantId: <code>{html.escape(service)}</code>\n"
        f"Dates: <code>{html.escape(date_from)}</code> - <code>{html.escape(date_to)}</code>\n"
        f"Matches: <code>{len(matches)}</code>\n\n"
        f"<pre>{html.escape(preview[:3500])}</pre>"
    )


def run_once(settings: Settings) -> tuple[int, list[str]]:
    payload, raw_text = fetch_luxmed(settings)
    terms = extract_terms(payload, raw_text)
    matches = matches_filters(terms, raw_text, settings)
    return len(terms), matches


def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    telegram = Telegram(settings.telegram_bot_token, settings.telegram_chat_id)
    last_signature = ""
    last_status = "Starting"
    last_auth_warning_key = ""
    last_http_auth_warning_key = ""

    telegram.send("Luxmed monitor started.")

    while not STOP:
        try:
            auth_key, auth_message = auth_token_status(settings)
            if auth_key.startswith(("missing", "invalid", "expired", "expiring")) and auth_key != last_auth_warning_key:
                telegram.send(f"<b>Luxmed auth warning</b>\n{html.escape(auth_message)}")
                last_auth_warning_key = auth_key

            for command in telegram.poll_commands():
                if command in {"/start", "/help"}:
                    telegram.send("Commands: /status, /check, /auth, /config")
                elif command == "/status":
                    telegram.send(last_status)
                elif command == "/auth":
                    telegram.send(html.escape(auth_message))
                elif command == "/config":
                    telegram.send(
                        "Luxmed monitor config:\n"
                        f"Interval: <code>{settings.poll_interval_seconds}s</code>\n"
                        f"Auth expiry warning: <code>{settings.auth_expiry_warn_minutes}m</code>\n"
                        f"Doctor regex: <code>{html.escape(settings.doctor_regex or '-')}</code>\n"
                        f"Text regex: <code>{html.escape(settings.match_text_regex or '-')}</code>"
                    )
                elif command == "/check":
                    total, matches = run_once(settings)
                    telegram.send(f"Manual check: terms={total}, matches={len(matches)}")

            if auth_key.startswith(("missing", "invalid", "expired")):
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                last_status = f"Last check: {now}; skipped because auth is {auth_key.split(':', 1)[0]}"
                LOGGER.warning("%s; %s", last_status, auth_message)
                raise StopIteration

            total, matches = run_once(settings)
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            last_status = f"Last check: {now}; terms={total}; matches={len(matches)}"
            LOGGER.info(last_status)

            if matches:
                current_signature = signature(matches)
                if settings.notify_on_every_match or current_signature != last_signature:
                    telegram.send(format_match_message(matches, settings))
                    last_signature = current_signature
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else "?"
            last_status = f"HTTP error from Luxmed/Telegram: {status_code}. Session cookies may be expired."
            LOGGER.exception(last_status)
            if status_code in {401, 403}:
                warning_key = f"http-auth:{status_code}"
                if warning_key != last_http_auth_warning_key:
                    telegram.send("Luxmed auth failed. Refresh LUXMED_COOKIE_HEADER from browser.")
                    last_http_auth_warning_key = warning_key
        except StopIteration:
            pass
        except Exception:
            last_status = "Luxmed monitor error; check container logs."
            LOGGER.exception(last_status)

        for _ in range(settings.poll_interval_seconds):
            if STOP:
                break
            time.sleep(1)

    telegram.send("Luxmed monitor stopped.")
    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    sys.exit(main())
