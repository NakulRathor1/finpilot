# FinPilot — Personal Finance & Investment Manager

FinPilot is a Flask + SQLite web application with separate workspaces for overview, budgeting and transactions, investments, savings goals, bills/subscriptions, and reports. It preserves the deep forest/emerald visual system and is responsive across desktop and mobile.

## Run locally

Python 3.10+ is required.

```bash
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`. SQLite creates `finpilot.db` automatically. Keep this file backed up; it contains user data. The app supports `FINPILOT_DB` to select a database path and `FINPILOT_SECRET` to set the session signing secret.

For a production-like local run, set a strong secret and use Gunicorn:

```bash
# PowerShell
$env:FINPILOT_SECRET = [guid]::NewGuid().ToString() + [guid]::NewGuid().ToString()
# macOS/Linux
# export FINPILOT_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
gunicorn --workers 2 --threads 4 --timeout 120 wsgi:app
```

## Deploy

- **Docker:** `docker build -t finpilot .` then run with `-p 5000:5000`, a persistent volume mounted at `/data`, and environment variables `FINPILOT_DB=/data/finpilot.db` and a strong `FINPILOT_SECRET`.
- **Render:** use the included `render.yaml` Blueprint. It configures Gunicorn, a generated session secret, and persistent SQLite storage.

Do not deploy with Flask's development server or `FLASK_DEBUG=1`. SQLite is suitable for a student showcase and a single-instance deployment; use a managed PostgreSQL database for multi-instance/high-concurrency production.

## Receipt scanning

On Bills & Subscriptions, choose **Scan bill / receipt**, select a clear JPG/PNG/WEBP image, wait for OCR, verify every suggested field, and save. OCR runs in the browser using Tesseract.js; the script is loaded from jsDelivr with an unpkg fallback, so the first scan requires internet access. Image preprocessing improves contrast and OCR text is retained in the transaction notes. If OCR cannot load or the image is unclear, all fields remain editable for manual entry. The image itself is not uploaded or stored. The receipt save endpoint atomically creates the transaction and, if selected, a linked paid bill plus its next recurring occurrence.

OCR is best-effort, not a guarantee: confirm merchant, date, category, and especially amount before saving.

## Features

- Session-based registration/login with hashed passwords
- Income/expense transaction entry, search, type/month filters, deletion
- Category budgets by month and spend progress
- Savings goals, target dates, contributions, editing/deletion
- Bills, recurring schedules, paid-state transaction recording
- Receipt OCR with reviewed transaction save and optional bill creation
- Investment portfolio with add/edit/delete, buy more, sell (avg cost basis), transaction history, catalog search, and best-effort delayed quotes
- Monthly reports and CSV export
- Persistent dark/light theme

## Checks

Run `python -m unittest discover -s tests` after installing requirements. The tests use a temporary SQLite database and exercise registration, transactions, budgets, goals, receipt save, bills, and reports.


## Investment market data

Quotes use the public Yahoo Finance chart endpoint (no API key). Prices are **delayed / best-effort**, not guaranteed real-time, and may fail when the provider rate-limits or is unreachable. Gold and silver should be entered as manual INR prices—do not treat commodity futures symbols as Indian spot metal prices. Always verify numbers before making decisions; FinPilot is a student finance tracker, not a brokerage.
