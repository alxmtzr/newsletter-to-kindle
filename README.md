# newsletter-to-kindle

Automated daily pipeline: TLDR newsletter email → clean EPUB with procedurally-generated cover → Kindle.

Runs as a single Docker container on a VPS (hourly cron, fully idempotent). Handles Amazon's asynchronous bounce flow with automatic retry and dead-letter notification. Extensible for other newsletter sources and delivery targets.

## How it works

```
IMAP (Gmail)  →  Parser  →  Newsletter  →  Cover (Pillow)  →  EPUB (ebooklib)  →  EPUBCheck  →  SMTP → @kindle.com
                                                                                                         ↓
                                                                                                   SQLite state DB
```

1. Every hour the script wakes up and checks Gmail IMAP for today's TLDR email.
2. The email is parsed — sponsors removed, tracking links unwrapped — and rendered as a clean EPUB with a randomly-generated cover (1200×1800, random colour and pattern each run).
3. The EPUB is validated with EPUBCheck, then emailed to your `@kindle.com` address.
4. Amazon processes it asynchronously. On failure a bounce email arrives; the script detects it on the next run and retries (max 3 attempts). After 3 failures you get a dead-letter notification with the EPUB attached for manual sideloading.

---

## One-time setup

### 1. Dedicated Gmail account

Create a new Gmail account (e.g. `yourname.tldr@gmail.com`):

1. Enable 2-Step Verification on the account.
2. Generate an [App Password](https://myaccount.google.com/apppasswords) — this is what goes in `.env`, **not** your regular password.
3. In Gmail Settings → Forwarding and POP/IMAP → enable **IMAP**.
4. Create a Gmail filter: `from:dan@tldrnewsletter.com` → apply label `tldr-newsletter` (defence-in-depth).
5. Subscribe to TLDR with the new address: [https://tldr.tech](https://tldr.tech)

### 2. Amazon approved senders

[Manage Your Content and Devices](https://www.amazon.com/mn/dcw/myx.html) → Preferences → Personal Document Settings → add the dedicated Gmail address to the approved senders list. **Without this every Kindle send silently fails.**

Your Kindle email address (`yourname@kindle.com`) is on the same page.

### 3. Healthchecks.io (optional but recommended)

Create a free check at [healthchecks.io](https://healthchecks.io), set the interval to 90 minutes, copy the ping URL. If the pipeline stops running, Healthchecks.io will email you.

### 4. Configure `.env`

```sh
cp .env.example .env
# Fill in all values — see .env.example for descriptions
```

| Variable | Description |
|---|---|
| `GMAIL_USER` | Dedicated Gmail address |
| `GMAIL_APP_PASSWORD` | 16-character app password (no spaces) |
| `KINDLE_EMAIL` | Your `name@kindle.com` address |
| `ALERT_RECIPIENT` | Your real email for failure/dead-letter notifications |
| `HEALTHCHECKS_URL` | Healthchecks.io ping URL (leave empty to disable) |

---

## Local development

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
| `python -m newsletter_kindle status` | Show recent newsletter processing state from SQLite |
| `python -m newsletter_kindle test-alert` | Send a test notification email to verify SMTP + alert config |
| `python -m newsletter_kindle test-kindle` | Send an invalid EPUB to Kindle to test the bounce/retry loop |
| `python -m newsletter_kindle cleanup --test` | Remove test-kindle entries from the state DB |
| `python -m newsletter_kindle cleanup --old 30` | Remove confirmed/dead entries older than 30 days |
| `python -m newsletter_kindle build <file.eml>` | Build an EPUB from a local `.eml` file — no IMAP, no SQLite, no send |

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

Prints a table of recent newsletter rows with their processing status, attempt count, and last error.

#### `test-kindle`

```sh
.venv/bin/python -m newsletter_kindle test-kindle [--db data/state.db]
```

Sends a deliberately invalid EPUB to your Kindle email to trigger an Amazon bounce. Use this to verify the full retry loop works end-to-end:

1. Run `test-kindle` — sends a corrupt EPUB, records it in SQLite as `sent`
2. Wait ~10 minutes for Amazon to send a bounce email to the dedicated Gmail
3. Run `python -m newsletter_kindle run` — the reconciler scans Gmail for the bounce, matches it by filename, marks it `confirmed_failed`
4. Run it again — the retry mechanism picks up the `confirmed_failed` row and resends
5. After 3 failed attempts the status becomes `dead_letter` and you get a notification email

```sh
# Step 1
.venv/bin/python -m newsletter_kindle test-kindle

# Step 3 (after ~10 min)
.venv/bin/python -m newsletter_kindle run
.venv/bin/python -m newsletter_kindle status
```

#### `test-alert`

```sh
.venv/bin/python -m newsletter_kindle test-alert
```

Sends a test email from the dedicated Gmail to `ALERT_RECIPIENT`. Use this to verify Gmail SMTP credentials and that notification emails reach your inbox before relying on the dead-letter mechanism.

#### `build`

```sh
.venv/bin/python -m newsletter_kindle build path/to/email.eml [--source tldr] [--output /tmp]
```

Parses a local `.eml` file and writes an EPUB to the output directory. Does not touch IMAP, SQLite, or Kindle — useful for testing the parser and cover generator against a real email.

### Tests

```sh
pytest                  # run all tests (85% coverage gate)
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
# Edit .env with real credentials
nano .env

docker compose up -d --build
```

### Commands

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

The cron job inside the container runs every hour and is fully idempotent — safe to run multiple times.

---

## Configuration (`config.yaml`)

Non-secret configuration lives in `config.yaml`. Secrets are in `.env` and referenced via `${VAR}`.

```yaml
sources:
  - name: tldr
    type: imap_email
    enabled: true                        # set to false to disable
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

senders:
  kindle:
    type: kindle_email
    to: ${KINDLE_EMAIL}
    from: ${GMAIL_USER}
```

---

## Extending

### Add a new newsletter source (e.g. TLDR AI)

Edit `config.yaml` — uncomment the `tldr-ai` entry and set `enabled: true`. If the email format differs from TLDR, add `src/newsletter_kindle/parsers/tldr_ai_parser.py` implementing the `Parser` ABC.

### Add a new delivery target (e.g. Kobo)

1. Write `src/newsletter_kindle/delivery/kobo_sender.py` implementing the `Sender` ABC (`send()` + `reconcile()`).
2. Register it in `src/newsletter_kindle/config.py`: add `"kobo_drop": KoboSender` to `SENDERS`.
3. Add the sender config to `config.yaml` and point a source's `pipeline:` at `"send:kobo"`.

### Add a non-email source (e.g. RSS)

Write `src/newsletter_kindle/sources/rss_source.py` implementing `Source.fetch_new()`, register in `SOURCES`, reference its `type:` in `config.yaml`.

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
| Kindle delivery | SMTP to `@kindle.com` via stdlib `smtplib` |
| State | SQLite (stdlib) |
| Logging | `structlog` (JSON to stdout) |
| Config | `pydantic-settings` (`.env`) + `pyyaml` (`config.yaml`) |
| Container | `python:3.12-slim` + `eclipse-temurin:21-jre-alpine`, ~250 MB, hourly cron |
| CI | GitHub Actions: ruff + mypy + pytest + gitleaks + docker build |
| Deploy | GHA SSH (`appleboy/ssh-action`) on merge to `main` |
| Secret scanning | `detect-secrets` + `gitleaks` pre-commit hooks |
