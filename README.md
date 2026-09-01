# BizLeadBot

A Telegram-first lead-extraction service. Send a public webpage URL, choose
how many pages to scan, and BizLeadBot scrapes the public HTML, extracts
useful links/titles/snippets, removes duplicates, and sends you back a CSV —
no terminal or command line needed.

BizLeadBot is the successor to the original `LeadFlow` console prototype,
rebuilt as a real Telegram bot service with a whitelist, an in-Telegram admin
panel, and a SQLite-backed architecture ready for future plans/quotas.

## Features

- 🤖 Telegram-only interface — no CLI required for end users
- 🔒 Whitelist-based access control
- 👑 In-Telegram admin panel (add/remove users, list users, check status, stats)
- 🕸️ Scraping engine with:
  - URL validation and SSRF protection (blocks localhost / private network IPs)
  - Request timeouts and HTTP error handling
  - Simple pagination following (up to a configurable page limit)
  - De-duplication of results
  - A configurable maximum result cap
- 🗄️ SQLite storage, isolated in a dedicated `database.py` module
- 📄 CSV export (UTF-8, Arabic/international-text safe)
- ☁️ Ready for GitHub + Render deployment

## Project structure

```
BizLeadBot/
├── bot.py            # Telegram handlers only
├── scraper.py         # Scraping engine (validation, fetch, extract, export)
├── database.py         # All SQLite access
├── config.py           # Environment-based configuration
├── requirements.txt
├── .env.example
├── .gitignore
├── render.yaml
├── data/               # SQLite database lives here (gitignored)
└── output/             # Generated CSV files (gitignored)
```

## Installation (local)

1. Clone the repository and enter it:
   ```bash
   git clone <your-repo-url>
   cd BizLeadBot
   ```
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Copy the example environment file and fill in your values:
   ```bash
   cp .env.example .env
   ```

## Environment variables

| Variable          | Description                                         | Default                 |
|-------------------|------------------------------------------------------|--------------------------|
| `BOT_TOKEN`       | Telegram bot token from [@BotFather](https://t.me/BotFather) | — (required) |
| `ADMIN_ID`        | Your numeric Telegram user ID (get it via `/whoami`) | — (required) |
| `DATABASE_PATH`   | Path to the SQLite database file                     | `data/bizleadbot.db`     |
| `MAX_PAGES`       | Max pages the scraper will follow per job             | `10`                     |
| `MAX_LEADS`       | Max results returned per job                          | `5000`                   |
| `REQUEST_TIMEOUT` | HTTP request timeout in seconds                       | `20`                     |
| `OUTPUT_DIR`      | Directory where CSV files are written                 | `output`                 |

Never commit your real `.env` file — it's already excluded via `.gitignore`.

## Running locally

```bash
python bot.py
```

The bot uses polling, so no public URL or webhook is required to run it locally.

## Admin setup

1. Message your bot with `/start`, then `/whoami` to get your Telegram ID.
2. Set that ID as `ADMIN_ID` in your `.env` (or Render environment variables).
3. Restart the bot. You can now use `/admin` to open the admin panel and
   whitelist yourself and other users.

## How users use the bot

1. `/start` — checks whitelist status.
2. If approved, send a public webpage URL (e.g. `https://example.com`).
3. Choose how many pages to scan via the inline buttons.
4. Wait for processing — BizLeadBot scrapes, cleans, and de-duplicates results.
5. Receive a summary message and a CSV file with the results.

## Deployment on Render

`render.yaml` defines a **worker** service (a polling Telegram bot has no
HTTP endpoint to serve, so a background worker is the right service type,
not a web service).

1. Push this repository to GitHub.
2. In Render, create a new Blueprint from the repo (it will read `render.yaml`).
3. Set `BOT_TOKEN` and `ADMIN_ID` as secret environment variables in the Render dashboard.
4. Deploy.

### A note on SQLite persistence on Render

SQLite is a single file on disk. On most hosting platforms, the filesystem
is **ephemeral** — it can be wiped on every redeploy or restart. `render.yaml`
attaches a small **persistent disk** mounted at the `data/` directory so the
database survives restarts and deploys.

This is fine for an MVP and moderate usage, but if BizLeadBot grows (multiple
instances, high write volume, need for backups/replication), plan to migrate
to a managed database such as Render's managed PostgreSQL.

## Security notes

- The bot token and admin ID are never hard-coded — only read from environment variables.
- The scraper validates URLs and resolves hostnames to block requests to
  localhost, private IP ranges, and link-local/metadata addresses (SSRF protection),
  including after redirects.
- The scraper does not attempt to bypass CAPTCHAs, logins, paywalls, or
  anti-bot protection — it only processes publicly reachable HTML.
- All scraping/database errors are caught and translated into user-friendly
  messages; stack traces are never sent to end users, only logged server-side.
- Page counts and result counts are capped via `MAX_PAGES` / `MAX_LEADS`.

## Roadmap (not implemented in V1)

- Free / Pro / Business plans with quotas
- Payment integration
- Email extraction from public pages
- Company/directory extraction and categorization
- Scheduled/recurring scraping jobs
- Job history view inside Telegram
- Monitoring and alerting

The `users` table already includes a `plan` column and a `jobs` table exists
for job history, so these can be layered on without a schema rewrite.
