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

## What it does

- Upload a PDF receipt from the browser
- Extract text locally with `pdfplumber`
- Optionally use OpenAI to pre-fill receipt fields
- File the PDF into a `YYYY-MM` Google Drive folder
- Append a row with a Drive link to your Google Sheet

  

https://github.com/user-attachments/assets/e18cc4fa-361e-414c-abbf-503624f9195b



## Local files

- `.env`: local configuration, not committed
- `credentials.json`: Google OAuth client, not committed
- `token.json`: Google OAuth token cache, not committed
- `uploads/`: temporary upload staging, not committed
- `receipt_hashes.json`: local duplicate-detection cache, not committed
