# Luxmed Appointment Monitor

This project monitors Luxmed Patient Portal appointment search results and sends Telegram notifications.

## Flow

1. Log in to Luxmed in the browser.
2. Install `luxmed_request_exporter.user.js` in Tampermonkey.
3. Open appointment search results.
4. If the exporter button says `Luxmed: click Search`, click Search in Luxmed again so the script can capture the `terms/index` request.
5. Click `Copy Luxmed VM env` or press `Alt+L`.
6. Replace `LUXMED_REQUEST_URL` in `.env` on the VM. Keep `LUXMED_COOKIE_HEADER` empty unless Luxmed blocks login/fetch without browser session cookies.
7. Run with Docker Compose.

To add another appointment search after the bot is already running:

1. Open the new Luxmed appointment search results.
2. Click Search in Luxmed so the exporter captures the latest `terms/index` request.
3. Press `Alt+J` / `Option+J` to copy a Telegram `/add_job ...` command.
4. Send that command to the Telegram bot.

The added search is saved in `STATE_FILE`, so it survives container restarts without editing `.env`.

The Tampermonkey exporter uses `Yauheni` as the default bot account name in copied `/add_job` commands. To change it in the browser console:

```js
localStorage.setItem("luxmed:accountName", "Second user")
```

## Important Inputs

The bot can generate `Authorization-Token` itself when `LUXMED_LOGIN` and `LUXMED_PASSWORD` are configured. The exporter copies the browser cookie header only as a commented fallback because Luxmed may require session or Incapsula anti-bot cookies on some requests.

The bot decodes `Authorization-Token`; when it is expired or will expire within `AUTH_EXPIRY_WARN_MINUTES`, it calls `/PatientPortal/Account/LogIn`, saves the new token in `STATE_FILE`, and continues polling.

When appointment windows appear in `termsForService.termsForDays[].terms[]`, the bot sends the available date/time, doctor, clinic, `serviceId`, `scheduleId`, `roomId`, `clinicId`, `doctorId`, the Luxmed results page, and the API request URL. Empty `termsForDays` means there are no available appointment windows yet, even when `termsInfoForDays` contains day status messages.

Each Telegram appointment item includes an `Open Luxmed result` link. Luxmed does not expose a plain static booking link in the saved HTML; the link opens the Results page and carries slot identifiers in the URL fragment so the right window can be identified quickly.

The Tampermonkey exporter also stores a `responseSummary` in the JSON backup after it sees the `terms/index` response. This summary includes `termsCount`, a preview of the first terms, and day status counters, so you can confirm it captured the correct search.

The search parameters are taken from the captured `LUXMED_REQUEST_URL`. For the current `terms/index` endpoint, the useful parameters are:

- `searchPlace.id`, `searchPlace.name`, `searchPlace.type`
- `serviceVariantId`
- `languageId`
- `searchDateFrom`, `searchDateTo`, `searchDatePreset`
- `referralId`, `referralTypeId`
- `processId`
- `nextSearch`
- `searchByMedicalSpecialist`
- `serviceVariantSource`
- `locationReplaced`
- `delocalized`

Optional filters:

- `LUXMED_DOCTOR_REGEX`
- `LUXMED_CLINIC_REGEX`
- `LUXMED_TIME_FROM` (`HH:MM`)
- `LUXMED_TIME_TO` (`HH:MM`)
- `LUXMED_MATCH_TEXT_REGEX`

For several independent searches, prefer `LUXMED_JOBS_JSON`. When it is set, the old single `LUXMED_REQUEST_URL` fields are ignored.

```env
LUXMED_JOBS_JSON='[
  {
    "name": "Psychiatry",
    "request_url": "https://portalpacjenta.luxmed.pl/PatientPortal/NewPortal/terms/index?...serviceVariantId=9158...",
    "doctor_regex": "",
    "clinic_regex": "",
    "time_from": "",
    "time_to": ""
  },
  {
    "name": "Dermatology - Antas",
    "request_url": "https://portalpacjenta.luxmed.pl/PatientPortal/NewPortal/terms/index?...serviceVariantId=4448...",
    "doctor_regex": "ANTAS",
    "clinic_regex": "Opolska|Lubelska",
    "time_from": "08:00",
    "time_to": "13:00"
  }
]'
```

Each `/jobs` entry includes two links:

- `Open Luxmed result` opens the Luxmed results page.
- `Open API request` opens the captured request for that exact job, so the second and later jobs are visible too.

For several Luxmed users, use `LUXMED_ACCOUNTS_JSON`. Each account has its own login/password, its own runtime token in `STATE_FILE`, and its own jobs.

```env
LUXMED_ACCOUNTS_JSON='[
  {
    "name": "Yauheni",
    "login": "first-user-login",
    "password": "first-user-password",
    "jobs": [
      {
        "name": "Psychiatry",
        "request_url": "https://portalpacjenta.luxmed.pl/PatientPortal/NewPortal/terms/index?...serviceVariantId=9158..."
      },
      {
        "name": "Dermatology",
        "request_url": "https://portalpacjenta.luxmed.pl/PatientPortal/NewPortal/terms/index?...serviceVariantId=4448..."
      }
    ]
  },
  {
    "name": "Second user",
    "login": "second-user-login",
    "password": "second-user-password",
    "jobs": [
      {
        "name": "Dermatology",
        "request_url": "https://portalpacjenta.luxmed.pl/PatientPortal/NewPortal/terms/index?...serviceVariantId=4448..."
      }
    ]
  }
]'
```

## Telegram Commands

The bot sends an inline button menu on startup and on `/help`. Buttons trigger the same commands below.

- `/status`
- `/check`
- `/jobs`
- `/add_job [account] [name] <Luxmed terms/index URL>`
- `/remove_job [account] <runtime job name or URL>`
- `/auth`
- `/login`
- `/config`
- `/interval <seconds>` (for example `/interval 3600`)
- `/live [seconds]` (enables one editable live status message and refreshes it every N seconds; for example `/live 5`)
- `/live_off`
- `/notify_once`
- `/notify_every`
- `/menu`
- `/set_cookie <full Cookie header>`
- `/help`

Runtime token/cookie updates are saved to `STATE_FILE` (`/data/luxmed_state.json` in Docker). With `LUXMED_LOGIN` and `LUXMED_PASSWORD`, the bot refreshes `Authorization-Token` automatically without editing `.env` or restarting the container.

With multiple accounts, token/cookie commands accept an optional account name first, for example:

```text
/login Yauheni
/set_auth Yauheni <Authorization-Token>
/set_cookie Second user Authorization-Token=...; XSRF-TOKEN=...
```

Runtime appointment searches can also target an account by name:

```text
/add_job Dermatology https://portalpacjenta.luxmed.pl/PatientPortal/NewPortal/terms/index?...
/add_job Yauheni Dermatology https://portalpacjenta.luxmed.pl/PatientPortal/NewPortal/terms/index?...
```

If the job name is omitted, the bot derives one from `serviceVariantId` and `searchDateFrom`.

Runtime searches can be removed by exact runtime job name or by exact captured URL:

```text
/remove_job Dermatology
/remove_job Yauheni Dermatology
```

`/remove_job` removes only jobs saved in `STATE_FILE`. Searches configured through `.env` (`LUXMED_REQUEST_URL`, `LUXMED_JOBS_JSON`, or `LUXMED_ACCOUNTS_JSON`) must be removed by editing `.env`.

`/interval` controls the normal background polling interval. `/live 5` is separate: while live mode is enabled, the bot checks and edits the live status every 5 seconds. The live status includes auth state, term/match counts, and the first matching slots with clickable Luxmed result links.

If Luxmed returns HTTP `429`, the bot pauses Luxmed requests for `RATE_LIMIT_BACKOFF_SECONDS` (default `300`) and keeps the live message updated with the retry time instead of repeatedly hitting the API.

Transient Telegram network failures (`ReadTimeout`, SSL EOF, remote disconnects) are treated as temporary delivery/polling issues. The bot logs a throttled warning without printing the Telegram bot token URL and keeps monitoring. Configure `TELEGRAM_TIMEOUT_SECONDS` if the VM network needs a different request timeout.

## Upstream Reference

Useful implementation notes were cross-checked against `dyrkin/luxmed-bot` in `/Users/yauhenisheima/Sources/Luxmed/luxmed-bot-upstream`.

The upstream project is a larger Scala/Akka Telegram bot with PostgreSQL persistence. It is too heavy to merge directly into this Python monitor, but it documents several Luxmed Patient Portal flows worth reusing:

- Dictionary endpoints:
  - `NewPortal/Dictionary/cities`
  - `NewPortal/Dictionary/serviceVariantsGroups`
  - `NewPortal/Dictionary/facilitiesAndDoctors`
- Search endpoint:
  - `NewPortal/terms/index`
- Booking chain:
  - `security/getforgerytoken`
  - `NewPortal/reservation/lockterm`
  - `NewPortal/reservation/confirm`
  - on failure after lock: `NewPortal/reservation/releaseterm?reservationId=<temporaryReservationId>`
- Rebooking chain:
  - `NewPortal/reservation/changeterm`
- Existing visits/history:
  - old API `Events`
  - old API `events/Visit/<reservationId>` for cancellation

The Python monitor now preserves the slot fields needed to build a future `reservation/lockterm` request payload, but it intentionally does not perform booking yet. Booking should stay behind an explicit Telegram confirmation step.

## Copy And Run

Create a Telegram bot via BotFather first, then get your chat id by sending a message to the bot and opening:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates"
```

Use `TELEGRAM_CHAT_ID` for one recipient, or `TELEGRAM_CHAT_IDS` / `TELEGRAM_USER_IDS` with comma-separated ids for several recipients.

Copy the project to the VM:

```bash
rsync -av --exclude .git --exclude .env --exclude .venv --exclude .chrome-profile \
  /Users/yauhenisheima/Sources/Luxmed/luxmed-api/ user@vm:/opt/luxmed-monitor/
```

On the VM:

```bash
cd /opt/luxmed-monitor
cp .env.example .env
nano .env
docker compose up -d --build
docker compose logs -f
```

Local login/API smoke test without Telegram:

```bash
cd /Users/yauhenisheima/Sources/Luxmed/luxmed-api
cp .env.example .env
${EDITOR:-nano} .env
docker compose build
docker compose run --rm --entrypoint python luxmed-bot luxmed_check.py
```

For this local check, `.env` needs at least:

```env
LUXMED_LOGIN=your-login
LUXMED_PASSWORD=your-password
LUXMED_REQUEST_URL='https://portalpacjenta.luxmed.pl/PatientPortal/NewPortal/terms/index?...'
```

Update after copying a new version:

```bash
cd /opt/luxmed-monitor
docker compose up -d --build
docker compose logs -f --tail=100
```
