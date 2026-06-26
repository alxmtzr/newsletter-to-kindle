# newsletter-to-kindle

> Automatically converts the TLDR newsletter into a clean EPUB and delivers it to your Kindle — every day, hands-free.

Runs as a single Docker container on a VPS. Parses today's TLDR email, generates a cover, validates the EPUB, and sends it to your Kindle email address. Handles Amazon's asynchronous bounce flow with automatic retry and dead-letter notification.

---

## Table of Contents

- [How it works](#how-it-works)
- [Prerequisites](#prerequisites)
- [One-time setup](#one-time-setup)
- [Local development](#local-development)
  - [Install](#install)
  - [Commands](#commands)
  - [Tests](#tests)
- [VPS deployment (Docker)](#vps-deployment-docker)
  - [First-time setup](#first-time-setup)
  - [Docker commands](#docker-commands)
  - [Automated deploy](#automated-deploy)
- [Configuration](#configuration-configyaml)
- [Extending](#extending)
  - [Add a new newsletter source](#add-a-new-newsletter-source-eg-tldr-ai)
  - [Add a new delivery target](#add-a-new-delivery-target-eg-kobo)
  - [Add a non-email source](#add-a-non-email-source-eg-rss)
- [Tech stack](#tech-stack)

---

## How it works

```
IMAP (Gmail)  →  Parser  →  Newsletter  →  Cover (Pillow)  →  EPUB (ebooklib)  →  EPUBCheck  →  SMTP → @kindle.com
                                                                                                         ↓
                                                                                                   SQLite state DB
```

1. Every 3 hours the script checks Gmail IMAP for today's TLDR email.
2. The email is parsed — sponsors removed, tracking links unwrapped — and rendered as a clean EPUB with a randomly-generated cover (1200×1800, random colour and pattern each run).
3. The EPUB is validated with EPUBCheck, then emailed to your `@kindle.com` address.
4. Amazon processes it asynchronously. On failure a bounce email arrives; the script detects it on the next run and retries (max 3 attempts). After 3 failures you get a dead-letter notification with the EPUB attached for manual sideloading.

---

## Prerequisites

- A **Hetzner VPS** (or any Linux VPS) with Docker installed
- A **dedicated Gmail account** for the newsletter (separate from your personal email)
- A **Kindle device** with a personal document email address (`@kindle.com`)
- A GitHub account to fork/clone this repo and configure deployment secrets

---

## One-time setup

### 1. Dedicated Gmail account

Create a new Gmail account (e.g. `yourname.tldr@gmail.com`):

1. Enable 2-Step Verification on the account.
2. Generate an [App Password](https://myaccount.google.com/apppasswords) — this is what goes in `.env`, **not** your regular password. Remove spaces from the 16-character password.
3. In Gmail Settings → Forwarding and POP/IMAP → enable **IMAP**.
4. Create a Gmail filter: `from:dan@tldrnewsletter.com` → apply label `tldr-newsletter` (keeps the inbox clean).
5. Subscribe to TLDR with the new address: [https://tldr.tech](https://tldr.tech)

### 2. Amazon approved senders

[Manage Your Content and Devices](https://www.amazon.com/mn/dcw/myx.html) → Preferences → Personal Document Settings → add the dedicated Gmail address to the approved senders list.

> **Without this step every Kindle send silently fails.** Your Kindle email address (`yourname@kindle.com`) is on the same page.

### 3. Healthchecks.io (optional but recommended)

Create a free check at [healthchecks.io](https://healthchecks.io), set the interval to 4 hours, copy the ping URL. If the pipeline stops running, Healthchecks.io will email you.

### 4. Configure `.env`

```sh
cp .env.example .env
# Fill in all values — see .env.example for descriptions
```

| Variable | Required | Description |
|---|---|---|
| `GMAIL_USER` | ✅ | Dedicated Gmail address |
| `GMAIL_APP_PASSWORD` | ✅ | 16-character app password (no spaces) |
| `KINDLE_EMAIL` | ✅ | Your `name@kindle.com` address |
| `ALERT_RECIPIENT` | ✅ | Your real email for failure/dead-letter notifications |
| `HEALTHCHECKS_URL` | — | Healthchecks.io ping URL (leave empty to disable) |
| `TZ` | — | Timezone for `status` display (e.g. `Europe/Berlin`, default `UTC`) |

### 5. GitHub Actions secrets (for automated deploy)

In your GitHub repo → Settings → Secrets and variables → Actions, add:

| Secret | Value |
|---|---|
| `VPS_HOST` | Your VPS IP or hostname |
| `VPS_USER` | SSH user on the VPS |
| `VPS_SSH_KEY` | Private SSH key content |
| `VPS_SSH_PORT` | SSH port (usually `22`) |

---

## Local development

### Install

```sh
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

### Commands

| Command | What it does |
|---|---|
| `python -m newsletter_kindle run --dry-run` | Full pipeline (IMAP → parse → EPUB) but **skips** Kindle send |
| `python -m newsletter_kindle run` | Full pipeline including Kindle send |
| `python -m newsletter_kindle status` | Show recent processing state from SQLite |
| `python -m newsletter_kindle test-alert` | Send a test notification email to verify SMTP + alert config |
| `python -m newsletter_kindle test-kindle` | Send an invalid EPUB to Kindle to test the bounce/retry loop |
| `python -m newsletter_kindle cleanup --test` | Remove test-kindle entries from the state DB |
| `python -m newsletter_kindle cleanup --old 30` | Remove confirmed/dead entries older than 30 days |
| `python -m newsletter_kindle build <file.eml>` | Build an EPUB from a local `.eml` file — no IMAP, no send |

#### `run`

```sh
.venv/bin/python -m newsletter_kindle run [--dry-run] [--config config.yaml] [--log-level INFO]
```

- `--dry-run` — connects to IMAP, parses, builds and validates the EPUB, then stops. Safe to run anytime without sending to Kindle.
- `--config` — path to `config.yaml` (default: `config.yaml` in cwd)
- `--log-level` — `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`)

#### `status`

```sh
.venv/bin/python -m newsletter_kindle status [--db data/state.db] [--limit 20]
```

Prints a table of recent newsletter rows with processing status, attempt count, and last error. Timestamps are shown in the timezone set by `TZ` env var (defaults to UTC).

#### `test-alert`

```sh
.venv/bin/python -m newsletter_kindle test-alert
```

Sends a test email from the dedicated Gmail to `ALERT_RECIPIENT`. Use this to verify Gmail SMTP credentials are working before relying on the dead-letter mechanism.

#### `test-kindle`

```sh
.venv/bin/python -m newsletter_kindle test-kindle [--db data/state.db]
```

Sends a deliberately invalid EPUB to your Kindle to trigger an Amazon bounce. Use this to verify the full retry loop end-to-end:

1. Run `test-kindle` — sends a corrupt EPUB, records it in SQLite as `sent`
2. Wait ~10 minutes for Amazon to bounce it back to the dedicated Gmail
3. Run `python -m newsletter_kindle run` — the reconciler detects the bounce, marks it `confirmed_failed`
4. Run again — the retry mechanism picks up the `confirmed_failed` row and resends
5. After 3 failed attempts the status becomes `dead_letter` and you get a notification email with the EPUB attached

```sh
.venv/bin/python -m newsletter_kindle test-kindle
# wait ~10 min for Amazon bounce
.venv/bin/python -m newsletter_kindle run
.venv/bin/python -m newsletter_kindle status
```

#### `build`

```sh
.venv/bin/python -m newsletter_kindle build path/to/email.eml [--source tldr] [--config config.yaml] [--output /tmp]
```

Parses a local `.eml` file and writes an EPUB to the output directory. Does not touch IMAP, SQLite, or Kindle — useful for testing the parser and cover generator against a real email offline.

#### `cleanup`

```sh
.venv/bin/python -m newsletter_kindle cleanup [--test] [--old DAYS] [--db data/state.db]
```

- `--test` — remove all `test-kindle` entries from the state DB
- `--old N` — remove confirmed/dead entries older than N days

### Tests

```sh
pytest                  # run all tests (75% coverage gate)
pytest -v -k test_cover # run specific tests
```

---

## VPS deployment (Docker)

### First-time setup

```sh
git clone https://github.com/alxmtzr/newsletter-to-kindle.git /opt/newsletter-to-kindle
cd /opt/newsletter-to-kindle
cp .env.example .env
chmod 600 .env
nano .env  # fill in real credentials

docker compose up -d --build
```

### Docker commands

| Command | What it does |
|---|---|
| `docker compose exec app python -m newsletter_kindle run --dry-run` | Dry run inside container |
| `docker compose exec app python -m newsletter_kindle run` | Real run inside container |
| `docker compose exec app python -m newsletter_kindle status` | Check processing state |
| `docker compose exec app python -m newsletter_kindle test-alert` | Test notification email |
| `docker compose exec app python -m newsletter_kindle test-kindle` | Test bounce/retry loop |
| `docker compose exec app python -m newsletter_kindle cleanup --test` | Remove test entries |
| `docker compose exec app python -m newsletter_kindle cleanup --old 30` | Remove entries older than 30 days |
| `docker logs -f newsletter-kindle` | Stream container logs |
| `docker compose up -d --build` | Rebuild and restart container |
| `docker compose down` | Stop container |

### Automated deploy

Push to `main` → CI runs (ruff + mypy + pytest + gitleaks + docker build) → if all pass → GitHub Actions SSHes into the VPS and redeploys automatically.

The cron job inside the container runs every 3 hours and is fully idempotent — safe to run multiple times with no side effects.

---

## Configuration (`config.yaml`)

Non-secret configuration lives in `config.yaml`. Secrets are in `.env` and referenced via `${VAR}`.

```yaml
sources:
  - name: tldr
    type: imap_email
    enabled: true                        # set to false to disable temporarily
    match:
      from: dan@tldrnewsletter.com
    parser: tldr_parser
    metadata:
      title_prefix: "TLDR"
      author: "Dan Ni"
      publisher: "TLDR Newsletter"
      subjects: [Newsletter, Technology]
      language: "en"
    pipeline: [build_epub, validate_epub, "send:kindle"]

  # Uncomment to add TLDR AI
  # - name: tldr-ai
  #   type: imap_email
  #   enabled: false
  #   match:
  #     from: dan@tldr.tech
  #   parser: tldr_parser
  #   metadata:
  #     title_prefix: "TLDR AI"
  #     author: "..."
  #   pipeline: [build_epub, validate_epub, "send:kindle"]

senders:
  kindle:
    type: kindle_email
    to: ${KINDLE_EMAIL}
    from: ${GMAIL_USER}
```

---

## Extending

### Add a new newsletter source (e.g. TLDR AI)

Edit `config.yaml` — uncomment the `tldr-ai` entry and set `enabled: true`. If the email format differs from TLDR, add `src/newsletter_kindle/parsers/tldr_ai_parser.py` implementing the `Parser` ABC, then wire it up in `_process_source()` in `src/newsletter_kindle/pipeline.py`.

### Add a new delivery target (e.g. Kobo)

1. Write `src/newsletter_kindle/delivery/kobo_sender.py` implementing the `Sender` ABC (`send()` + `reconcile()`).
2. Instantiate it in `src/newsletter_kindle/pipeline.py` alongside the existing `KindleEmailSender`.
3. Add any required credentials to `.env` and `.env.example`.

### Add a non-email source (e.g. RSS)

1. Write `src/newsletter_kindle/sources/rss_source.py` implementing `Source.fetch_new()`.
2. Add a new source block in `config.yaml` and wire it up in `_process_source()` in `pipeline.py`.

---

## Tech stack

| Concern | Choice |
|---|---|
| Language | Python 3.12, venv, pyproject.toml |
| Email ingestion | Gmail IMAP + `imap-tools` |
| HTML parsing | `beautifulsoup4` |
| EPUB generation | `ebooklib` (EPUB 3) |
| Cover art | `Pillow` — random colour + pattern each run, Paperwhite-optimised brightness |
| EPUB validation | EPUBCheck official W3C jar |
| Kindle delivery | SMTP to `@kindle.com` via stdlib `smtplib` (SSL port 465) |
| State | SQLite (stdlib) |
| Logging | `structlog` (JSON to stdout) |
| Config | `pydantic-settings` (`.env`) + `pyyaml` (`config.yaml`) |
| Container | `python:3.12-slim` + `eclipse-temurin:21-jre-alpine`, ~250 MB, cron every 3 hours |
| CI | GitHub Actions: ruff + mypy + pytest + gitleaks + docker build |
| Deploy | GHA SSH (`appleboy/ssh-action`) on merge to `main` |
| Secret scanning | `detect-secrets` + `gitleaks` pre-commit hooks |
