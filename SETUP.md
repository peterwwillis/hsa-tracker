# HSA Receipt Tracker Setup

## Prerequisites

- macOS or another environment that can run `uv` and Python 3.13+
- [uv](https://docs.astral.sh/uv/) installed
- A Google account that owns the destination Drive folder and Sheet

## 1. Install dependencies

```bash
uv sync
```

## 2. Create a Google Cloud project

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project for this app.
3. Enable both APIs:
   - Google Drive API
   - Google Sheets API

## 3. Create desktop OAuth credentials

A **Desktop app OAuth client ID** is a Google Cloud credential type designed for
applications that run locally on your computer (as opposed to credentials for web
servers or service accounts). It lets the app open a browser tab where you sign in
with your Google account and grant access, then stores the resulting token locally
so you do not need to sign in again on the next run.

To create one:

1. Go to **APIs & Services → Credentials** in [Google Cloud Console](https://console.cloud.google.com/).
2. If prompted, configure the **OAuth consent screen** (choose *External* for personal accounts, fill in the app name and your email).
3. Click **+ Create Credentials → OAuth client ID**.
4. Under *Application type*, choose **Desktop app**.
5. Give it any name (e.g. "HSA Tracker") and click **Create**.
6. Click **Download JSON** on the confirmation dialog (or the ⬇ icon next to it in the credentials list).
7. Save the downloaded file as `credentials.json` in the repo root, next to `app.py`.

If Google shows an unverified-app warning during the first login, that is expected for a personal desktop OAuth client.

## 4. Create the destination Google Sheet and Drive folder

1. Create or choose a Google Sheet that will hold receipt rows.
2. Create or choose a Google Drive folder where monthly receipt folders should live.
3. Copy the Sheet ID from the spreadsheet URL.
4. Copy the Drive folder ID from the folder URL.

## 5. Configure the app

```bash
cp .env.example .env
```

Open `.env` in a text editor and fill in the required values:

- `SPREADSHEET_ID` – the ID from your Google Sheet URL
  (e.g. `https://docs.google.com/spreadsheets/d/<ID>/edit`)
- `DRIVE_FOLDER_ID` – the ID from your Google Drive folder URL
  (e.g. `https://drive.google.com/drive/folders/<ID>`)
- `SHEET_NAME` – the tab name inside the spreadsheet (default: `Sheet1`)
- `OPENAI_API_KEY` – your OpenAI API key if you want AI-assisted field
  extraction; leave blank to use manual entry only.
  Get a key at <https://platform.openai.com/api-keys>.

## 6. Run locally

```bash
uv run app.py
```

On the first run:

1. A browser window opens for Google sign-in.
2. Sign in with the Google account that owns the Sheet and Drive folder.
3. Approve access.
4. The app stores `token.json` locally for future runs.

Then open <http://localhost:5050>.

## 7. Run as an always-on macOS service

The repo includes a reusable `launchd` plist template at `com.pjhoberman.hsa-tracker.plist`.

Before loading it, replace these placeholder values in the plist:

- `__WORKING_DIRECTORY__`: absolute path to your clone, for example `/Users/you/Projects/hsa-tracker`
- `__UV_BIN__`: absolute path to `uv`, for example `/opt/homebrew/bin/uv`
- `__LOG_PATH__`: absolute log file path, for example `/Users/you/Library/Logs/hsa-tracker.log`

Then install or restart the agent:

```bash
cp /absolute/path/to/hsa-tracker/com.pjhoberman.hsa-tracker.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.pjhoberman.hsa-tracker.plist
launchctl load ~/Library/LaunchAgents/com.pjhoberman.hsa-tracker.plist
```

If this is the first install, `launchctl unload` may report that the service was not loaded yet. That is safe to ignore.

Useful commands:

```bash
launchctl unload ~/Library/LaunchAgents/com.pjhoberman.hsa-tracker.plist
launchctl load ~/Library/LaunchAgents/com.pjhoberman.hsa-tracker.plist
tail -f ~/Library/Logs/hsa-tracker.log
```

## Troubleshooting

**`credentials.json not found`**
Place the downloaded desktop OAuth JSON in the repo root as `credentials.json`.

**Missing configuration error**
Copy `.env.example` to `.env` and fill in the Google IDs before filing receipts.

**`Token has been expired or revoked`**
Delete `token.json` and run the app again to re-authenticate.

**Google returns `403`**
Make sure you enabled both APIs and authenticated with the account that owns the target Sheet and Drive folder.

**AI extraction does not run**
Leave `OPENAI_API_KEY` blank to use manual entry, or set it to enable OpenAI-based field extraction.
