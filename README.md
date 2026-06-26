# newsletter-to-kindle

Automated daily pipeline: TLDR newsletter email → clean EPUB with cover art → Kindle.

Runs as a single Docker container on a VPS (hourly cron, fully idempotent). Handles Amazon's asynchronous bounce flow with automatic retry and dead-letter notification. Extensible for other newsletter sources and delivery targets.

## How it works

```
IMAP (Gmail)  →  Parser  →  Newsletter  →  Cover (Pillow)  →  EPUB (ebooklib)  →  EPUBCheck  →  SMTP → @kindle.com
                                                                                         ↓
                                                                                   SQLite state DB
```

1. Every hour the script wakes up, checks Gmail IMAP for new TLDR emails.
2. Each email is parsed, sanitized (sponsors removed, tracking links unwrapped), and rendered as a clean EPUB with a procedurally-generated cover (1600×2400, colour-seeded by date).
3. The EPUB is validated with EPUBCheck, then emailed to your `@kindle.com` address.
4. Amazon processes it asynchronously. If it fails, a bounce email arrives; the script detects it on the next run and retries (max 3 attempts). After 3 failures you get a notification with the EPUB attached for manual sideloading.

## Prerequisites

Before running, complete these one-time manual steps:

1. **Create a dedicated Gmail account** (e.g. `yourname.tldr@gmail.com`). Enable 2FA. Generate an [app password](https://myaccount.google.com/apppasswords).
2. **Gmail filter**: from `dan@tldrnewsletter.com` → apply label `tldr-newsletter` (defence-in-depth, keeps the inbox clean).
3. **Amazon approved senders**: [Manage Your Content and Devices](https://www.amazon.com/mn/dcw/myx.html) → Preferences → Personal Document Settings → add the dedicated Gmail. **Without this every send silently fails.**
4. **Subscribe to TLDR** with the new Gmail: [https://tldr.tech](https://tldr.tech)
5. **Healthchecks.io** (optional but recommended): create a free check at [healthchecks.io](https://healthchecks.io), set interval to 90 min, copy the ping URL.
6. **Create `.env`** — copy `.env.example` and fill in your values:
   ```sh
   cp .env.example .env
   # edit .env
   ```
7. **Set git identity** (local to this repo, keeps your work email off public commits):
   ```sh
   git config user.name "alxmtzr"
   git config user.email "dev.alxmtzr@gmail.com"
   ```
8. **Install pre-commit hooks**:
   ```sh
   pip install pre-commit && pre-commit install
   ```

## Running locally

```sh
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# Dry run (connects to IMAP, builds EPUB, skips the SMTP send)
python -m newsletter_kindle run --dry-run
# Check state
python -m newsletter_kindle status
```

## Running on VPS (Docker)

```sh
# One-time: clone and configure
git clone https://github.com/alxmtzr/newsletter-to-kindle.git /opt/newsletter-to-kindle
cd /opt/newsletter-to-kindle
cp .env.example .env && chmod 600 .env
# edit /opt/newsletter-to-kindle/.env with real credentials

# Start
docker compose up -d --build

# Logs
docker logs -f newsletter-kindle

# Status
docker compose exec app python -m newsletter_kindle status
```

Deploy is automated: push to `main` → GitHub Actions SSHes into the VPS, `git pull`, `docker compose build`, `docker compose up -d`.

## Adding TLDR AI (or another source)

Edit `config.yaml` and set `enabled: true` on the `tldr-ai` entry (already there as a template). No code changes needed if the email format is the same as TLDR.

## Adding a new delivery target

1. Write `src/newsletter_kindle/delivery/your_sender.py` implementing the `Sender` ABC (`send()` + optional `reconcile()`).
2. Register it in `src/newsletter_kindle/config.py`: add `"your_sender": YourSender` to the `SENDERS` dict.
3. Reference it in `config.yaml`:
   ```yaml
   senders:
     mykobo:
       type: your_sender
       ...
   ```
4. Point a source's `pipeline:` at `"send:mykobo"`.

## Tech stack

| Concern | Choice |
|---|---|
| Language | Python 3.12 |
| Email | Gmail IMAP + SMTP via `imap-tools` / `smtplib` |
| Parsing | `beautifulsoup4` |
| EPUB | `ebooklib` (EPUB 3) |
| Cover art | `Pillow` (procedural, deterministic, date-seeded) |
| EPUB validation | EPUBCheck (official W3C jar, strict EPUB 3 mode) |
| State | SQLite (stdlib) |
| Logging | `structlog` (JSON to stdout) |
| Config | `pydantic-settings` (.env secrets) + `pyyaml` (config.yaml) |
| Container | Alpine JRE + Python 3.12-slim, multi-stage, ~250 MB |
| Scheduling | cron-inside-Docker, hourly |
| CI | GitHub Actions (pytest + ruff + mypy + gitleaks + docker build) |
| Deploy | GHA SSH (`appleboy/ssh-action`) |
