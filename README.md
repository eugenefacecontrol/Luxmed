# Luxmed Appointment Monitor

This project monitors Luxmed Patient Portal appointment search results and sends Telegram notifications.

## Flow

1. Log in to Luxmed in the browser.
2. Install `luxmed_request_exporter.user.js` in Tampermonkey.
3. Open appointment search results.
4. If the exporter button says `Luxmed: click Search`, click Search in Luxmed again so the script can capture the `terms/index` request.
5. Click `Copy Luxmed VM env` or press `Alt+L`.
6. Replace only `LUXMED_REQUEST_URL` and `LUXMED_COOKIE_HEADER` in `.env` on the VM.
7. Run with Docker Compose.

## Important Inputs

The most important value is the authenticated `Authorization-Token` cookie. The exporter copies the full visible cookie header because Luxmed may also require `XSRF-TOKEN`, `RefreshToken`, `LXToken`, `PatientPortalDeviceId`, or Incapsula anti-bot cookies.

The bot decodes `Authorization-Token` and sends a Telegram warning when it is expired or will expire within `AUTH_EXPIRY_WARN_MINUTES`.

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

## Telegram Commands

- `/status`
- `/check`
- `/auth`
- `/config`
- `/set_cookie <full Cookie header>`
- `/set_auth <Authorization-Token>`
- `/set_xsrf <XSRF-TOKEN>`
- `/set_refresh <RefreshToken>`
- `/set_lx <LXToken>`
- `/help`

Runtime token updates from Telegram are saved to `STATE_FILE` (`/data/luxmed_state.json` in Docker). This lets the bot continue after auth expiry without editing `.env` or restarting the container.

## Copy And Run

Create a Telegram bot via BotFather first, then get your chat id by sending a message to the bot and opening:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates"
```

Use `TELEGRAM_CHAT_ID` for one recipient, or `TELEGRAM_CHAT_IDS` / `TELEGRAM_USER_IDS` with comma-separated ids for several recipients.

Copy the project to the VM:

```bash
rsync -av --exclude .git --exclude .env --exclude .venv --exclude .chrome-profile \
  /Users/yauhenisheima/Sources/Luxmed/ user@vm:/opt/luxmed-monitor/
```

On the VM:

```bash
cd /opt/luxmed-monitor
cp .env.example .env
nano .env
docker compose up -d --build
docker compose logs -f
```

Update after copying a new version:

```bash
cd /opt/luxmed-monitor
docker compose up -d --build
docker compose logs -f --tail=100
```
