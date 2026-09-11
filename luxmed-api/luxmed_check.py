import json
import os
import sys
from pathlib import Path

import requests

from luxmed_bot import (
    SearchJob,
    Settings,
    extract_terms,
    fetch_luxmed,
    login_luxmed,
    matches_filters,
    parse_jobs_from_env,
    term_identifier,
    upsert_cookie,
)


def load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key.strip(), value)


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing {name}")
    return value


def build_settings() -> Settings:
    try:
        jobs = parse_jobs_from_env()
    except RuntimeError:
        jobs = [
            SearchJob(
                name=os.getenv("LUXMED_JOB_NAME", "local-check"),
                request_url=required("LUXMED_REQUEST_URL"),
                doctor_regex=os.getenv("LUXMED_DOCTOR_REGEX") or None,
                clinic_regex=os.getenv("LUXMED_CLINIC_REGEX") or None,
                time_from=os.getenv("LUXMED_TIME_FROM") or None,
                time_to=os.getenv("LUXMED_TIME_TO") or None,
                match_text_regex=os.getenv("LUXMED_MATCH_TEXT_REGEX") or None,
            )
        ]

    return Settings(
        telegram_bot_token="local-check",
        telegram_target_ids=["0"],
        luxmed_login=required("LUXMED_LOGIN"),
        luxmed_password=required("LUXMED_PASSWORD"),
        luxmed_cookie_header=os.getenv("LUXMED_COOKIE_HEADER") or None,
        luxmed_base_uri=os.getenv("LUXMED_BASE_URI", "https://portalpacjenta.luxmed.pl"),
        jobs=jobs,
        poll_interval_seconds=60,
        notify_on_every_match=False,
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        auth_expiry_warn_minutes=2,
        state_file="/tmp/luxmed_state.json",
    )


def main() -> int:
    load_dotenv()
    settings = build_settings()
    cookie_header = settings.luxmed_cookie_header or ""

    print("Logging in to Luxmed...")
    token = login_luxmed(settings, cookie_header)
    cookie_header = upsert_cookie(cookie_header, "Authorization-Token", token)
    print(f"Login OK. Token length: {len(token)}")

    for job in settings.jobs:
        print(f"Fetching appointment search: {job.name}")
        payload, raw_text = fetch_luxmed(settings, job, cookie_header)
        terms = extract_terms(payload, raw_text)
        matches = matches_filters(terms, raw_text, job)

        print(f"Total terms: {len(terms)}")
        print(f"Matching terms: {len(matches)}")

        for index, term in enumerate(matches[:10], start=1):
            if term.get("rawText"):
                print(f"{index}. {term['rawText'][:200]}")
                continue
            print(
                f"{index}. {term.get('dateTimeFrom')} - {term.get('dateTimeTo')} | "
                f"{term.get('doctorName')} | {term.get('clinic') or term.get('clinicGroup')} | "
                f"{term_identifier(term)}"
            )

        if len(matches) > 10:
            print(f"...and {len(matches) - 10} more")

        if isinstance(payload, dict):
            print("Response summary:")
            print(json.dumps({key: payload.get(key) for key in ("success", "pMode", "correlationId")}, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        print(f"HTTP error: {status}", file=sys.stderr)
        if exc.response is not None:
            print(exc.response.text[:1000], file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
