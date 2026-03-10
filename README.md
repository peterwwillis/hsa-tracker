# HSA Receipt Tracker

Local Flask app for filing HSA receipts into Google Drive and logging them in Google Sheets.

## Quick start

```bash
uv sync
cp .env.example .env
uv run app.py
```

You will also need:
- a Google Drive folder where receipts should be stored
- a Google Sheet that receives the receipt rows
- a desktop OAuth client downloaded as `credentials.json`

`SETUP.md` covers the full Google Cloud, OAuth, and `launchd` setup.

## Single-file binaries (macOS, Windows, Linux)

Package with Nuitka:

```bash
uv sync --extra build
uv run python -m nuitka --onefile --standalone \
  --include-data-dir=templates=templates \
  --output-filename=hsa-tracker \
  app.py
```

The binary is written to the repo root (`hsa-tracker` on macOS/Linux, `hsa-tracker.exe` on Windows). Nuitka also creates a `hsa-tracker.build/` directory that can be removed after the build.

Runtime files live next to the binary by default (`.env`, `credentials.json`, `token.json`, `receipt_hashes.json`, `uploads/`). To keep them somewhere else, set `HSA_DATA_DIR=/path/to/writable/dir` before launching the binary.

## What it does

- Upload a PDF receipt from the browser
- Extract text locally with `pdfplumber`
- Optionally use OpenAI to pre-fill receipt fields
- File the PDF into a `YYYY-MM` Google Drive folder
- Append a row with a Drive link to your Google Sheet

## Local files

- `.env`: local configuration, not committed
- `credentials.json`: Google OAuth client, not committed
- `token.json`: Google OAuth token cache, not committed
- `uploads/`: temporary upload staging, not committed
- `receipt_hashes.json`: local duplicate-detection cache, not committed
