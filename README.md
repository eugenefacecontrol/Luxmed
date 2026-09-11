# Luxmed Appointment Monitor

This project monitors Luxmed Patient Portal appointment search results and sends Telegram notifications.

## Flow

1. Log in to Luxmed in the browser.
2. Install `luxmed_request_exporter.user.js` in Tampermonkey.
3. Open appointment search results.
4. Click `Copy Luxmed VM env` or press `Alt+L`.
5. Paste the copied env values into `.env` on the VM.
6. Run with Docker Compose.

## Important Inputs

The most important value is the authenticated `Authorization-Token` cookie. The exporter copies the full visible cookie header because Luxmed may also require `XSRF-TOKEN`, `RefreshToken`, `LXToken`, `PatientPortalDeviceId`, or Incapsula anti-bot cookies.

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
- `/config`
- `/help`

## Copy And Run

Create a Telegram bot via BotFather first, then get your chat id by sending a message to the bot and opening:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates"
```

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
