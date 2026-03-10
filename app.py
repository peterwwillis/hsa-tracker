"""
HSA Receipt Tracker
Drop a PDF receipt → extracts data → files it in Google Drive → logs it in your Sheet.
"""

import hashlib
import os
import importlib
import importlib.abc
import importlib.util
import sys
from types import ModuleType

os.environ.setdefault("CHARSET_NORMALIZER_FORCE_PUREPY", "1")

# Ensure charset_normalizer never fails on missing mypyc extensions packaged by PyInstaller.
# We redirect any charset_normalizer.*__mypyc import to the pure-Python fallback module.
class _MypycRedirector(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        parts = fullname.split(".")
        if len(parts) >= 2 and parts[0] == "charset_normalizer" and parts[-1].endswith("__mypyc"):
            return importlib.util.spec_from_loader(fullname, self)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        fallback = None
        for candidate in ("charset_normalizer.md", "charset_normalizer.cd"):
            try:
                fallback = importlib.import_module(candidate)
                break
            except ImportError:
                pass

        if fallback is None:
            fallback = ModuleType("charset_normalizer_stub")
            def _return_empty_list(*args, **kwargs):
                return []
            fallback.from_bytes = _return_empty_list
            fallback.from_fp = _return_empty_list
            fallback.from_path = _return_empty_list
            fallback.is_binary = lambda *args, **kwargs: False
        module.__dict__.update(fallback.__dict__)


sys.meta_path.insert(0, _MypycRedirector())

import json
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import pdfplumber
from werkzeug.utils import secure_filename

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def _runtime_paths():
    """Resolve bundle (read-only) and data (writable) roots.

    When packaged with PyInstaller, code and templates live under the extracted
    bundle path (sys._MEIPASS) while the executable sits beside a writable
    directory. We default writable data to the executable's directory but allow
    overriding via HSA_DATA_DIR.
    """
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        data_root = Path(os.getenv("HSA_DATA_DIR", Path(sys.executable).resolve().parent))
    else:
        bundle_root = Path(__file__).parent
        data_root = Path(os.getenv("HSA_DATA_DIR", bundle_root))
    return bundle_root, data_root


BUNDLE_DIR, DATA_DIR = _runtime_paths()
DATA_DIR.mkdir(parents=True, exist_ok=True)
# Load env from the bundled/writable data dir first, then allow local overrides.
load_dotenv(DATA_DIR / ".env")
load_dotenv()

TEMPLATE_DIR = BUNDLE_DIR / "templates"
app = Flask(__name__, template_folder=str(TEMPLATE_DIR))
app.config["UPLOAD_FOLDER"] = DATA_DIR / "uploads"
app.config["UPLOAD_FOLDER"].mkdir(exist_ok=True, parents=True)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
HASH_STORE_PATH = DATA_DIR / "receipt_hashes.json"


# ---------------------------------------------------------------------------
# Configuration — override via .env or environment variables
# ---------------------------------------------------------------------------
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "").strip()
DRIVE_PARENT_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "").strip()
SHEET_NAME = os.getenv("SHEET_NAME", "Sheet1").strip() or "Sheet1"

# Optional — set OPENAI_API_KEY to enable auto-extraction
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


def missing_google_config() -> list[str]:
    """Return required Google config keys that are still unset."""
    missing = []
    if not SPREADSHEET_ID:
        missing.append("SPREADSHEET_ID")
    if not DRIVE_PARENT_FOLDER_ID:
        missing.append("DRIVE_FOLDER_ID")
    return missing


# ---------------------------------------------------------------------------
# Google Auth
# ---------------------------------------------------------------------------
def get_google_creds():
    """Get or refresh Google OAuth2 credentials (desktop app flow)."""
    creds = None
    token_path = DATA_DIR / "token.json"
    creds_path = DATA_DIR / "credentials.json"

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                raise FileNotFoundError(
                    "credentials.json not found. See SETUP.md for instructions."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=8081)
        token_path.write_text(creds.to_json())
        os.chmod(token_path, 0o600)

    return creds


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------
def file_sha256(filepath: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_hash_store() -> dict:
    """Load the hash→metadata store from disk."""
    if HASH_STORE_PATH.exists():
        return json.loads(HASH_STORE_PATH.read_text())
    return {}


def save_hash_store(store: dict):
    """Persist the hash→metadata store to disk."""
    HASH_STORE_PATH.write_text(json.dumps(store, indent=2))


def check_duplicate(file_hash: str) -> dict | None:
    """Return previous receipt metadata if this hash was already filed, else None."""
    store = load_hash_store()
    return store.get(file_hash)


def record_hash(file_hash: str, filename: str, vendor: str, service_date: str):
    """Record a filed receipt's hash."""
    store = load_hash_store()
    store[file_hash] = {
        "filename": filename,
        "vendor": vendor,
        "service_date": service_date,
        "filed_at": datetime.now().isoformat(),
    }
    save_hash_store(store)


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------
def extract_pdf_text(filepath: Path) -> str:
    """Extract all text from a PDF."""
    text = ""
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text.strip()


# ---------------------------------------------------------------------------
# OpenAI-based field extraction (optional)
# ---------------------------------------------------------------------------
def extract_fields_with_openai(text: str, filename: str) -> dict | None:
    """Use OpenAI to pull structured fields from receipt text. Returns None on failure."""
    if not OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Extract receipt/invoice information from this text. "
                        "Return ONLY valid JSON (no markdown fences) with these fields:\n"
                        '- "vendor": company or provider name\n'
                        '- "service_date": date of service, format M/D/YY (e.g. "3/15/25")\n'
                        '- "amount": dollar amount as a number string, no $ sign\n'
                        '- "date_paid": payment date if shown (same format), or ""\n'
                        '- "paid_via": payment method if mentioned, or ""\n'
                        '- "notes": very brief description of what was purchased/service, or ""\n\n'
                        f'Filename: "{filename}"\n\n'
                        f"Receipt text:\n{text[:4000]}"
                    ),
                }
            ],
        )
        raw = response.choices[0].message.content.strip()
        # Handle potential markdown fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(raw)
    except Exception as e:
        print(f"[OpenAI extraction] {e}")
        return None


# ---------------------------------------------------------------------------
# Google Drive helpers
# ---------------------------------------------------------------------------
def get_or_create_month_folder(drive_service, date_str: str):
    """Find or create the YYYY-MM folder under the HSA parent folder."""
    try:
        parts = date_str.strip().split("/")
        month = int(parts[0])
        if len(parts) >= 3 and parts[2]:
            year = int(parts[2])
            year = year + 2000 if year < 100 else year
        else:
            year = datetime.now().year
        folder_name = f"{year}-{month:02d}"
    except (ValueError, IndexError):
        now = datetime.now()
        folder_name = f"{now.year}-{now.month:02d}"

    # Check if folder already exists
    query = (
        f"name = '{folder_name}' and "
        f"'{DRIVE_PARENT_FOLDER_ID}' in parents and "
        f"mimeType = 'application/vnd.google-apps.folder' and "
        f"trashed = false"
    )
    results = (
        drive_service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )
    folders = results.get("files", [])
    if folders:
        return folders[0]["id"], folder_name

    # Create folder
    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [DRIVE_PARENT_FOLDER_ID],
    }
    folder = drive_service.files().create(body=metadata, fields="id").execute()
    return folder["id"], folder_name


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    has_ai = bool(OPENAI_API_KEY)
    return render_template("index.html", has_ai=has_ai)


@app.route("/upload", methods=["POST"])
def upload():
    """Accept PDF, extract text, optionally auto-extract fields."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    filename = secure_filename(file.filename or "")

    if not filename:
        return jsonify({"error": "Empty filename"}), 400
    if not filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported right now"}), 400

    filepath = app.config["UPLOAD_FOLDER"] / filename
    file.save(filepath)

    # Check for duplicate PDF
    file_hash = file_sha256(filepath)
    duplicate = check_duplicate(file_hash)

    try:
        text = extract_pdf_text(filepath)
    except Exception as e:
        filepath.unlink(missing_ok=True)
        return jsonify({"error": f"PDF extraction failed: {e}"}), 500

    fields = extract_fields_with_openai(text, filename) or {
        "vendor": "",
        "service_date": "",
        "amount": "",
        "date_paid": "",
        "paid_via": "",
        "notes": "",
    }

    result = {
        "filename": filename,
        "text": text[:6000],
        "fields": fields,
        "file_hash": file_hash,
    }
    if duplicate:
        result["duplicate"] = duplicate

    return jsonify(result)


@app.route("/submit", methods=["POST"])
def submit():
    """Upload PDF to Drive and append a row to the Sheet."""
    data = request.get_json(silent=True) or {}
    missing_config = missing_google_config()
    if missing_config:
        missing_keys = ", ".join(missing_config)
        return jsonify(
            {
                "error": (
                    f"Missing configuration: {missing_keys}. "
                    "Copy .env.example to .env and fill in your Google IDs."
                )
            }
        ), 400

    filename = data.get("filename", "")
    file_hash = data.get("file_hash", "")
    filepath = app.config["UPLOAD_FOLDER"] / filename

    if not filepath.exists():
        return jsonify({"error": "File not found — please re-upload."}), 400

    try:
        creds = get_google_creds()
        drive_svc = build("drive", "v3", credentials=creds)
        sheets_svc = build("sheets", "v4", credentials=creds)

        # 1. Upload to the correct YYYY-MM folder
        folder_id, folder_name = get_or_create_month_folder(
            drive_svc, data.get("service_date", "")
        )
        file_meta = {"name": filename, "parents": [folder_id]}
        media = MediaFileUpload(str(filepath), mimetype="application/pdf")
        uploaded = (
            drive_svc.files()
            .create(body=file_meta, media_body=media, fields="id,webViewLink")
            .execute()
        )

        # 2. Append row to the Google Sheet
        row = [
            data.get("vendor", ""),
            data.get("service_date", ""),
            data.get("amount", ""),
            data.get("date_paid", ""),
            data.get("paid_via", ""),
            "",  # Invoice — usually blank
            f'=HYPERLINK("{uploaded.get("webViewLink", "")}", "{filename}")',  # Receipt
            data.get("notes", ""),
        ]
        sheets_svc.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A:H",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()

        # 3. Record hash to prevent future duplicates
        if file_hash:
            record_hash(
                file_hash,
                filename,
                data.get("vendor", ""),
                data.get("service_date", ""),
            )

        # 4. Clean up local temp file
        filepath.unlink(missing_ok=True)

        return jsonify(
            {
                "success": True,
                "folder": folder_name,
                "drive_link": uploaded.get("webViewLink", ""),
                "message": f"Filed in {folder_name} and added to spreadsheet.",
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    print("\n  HSA Receipt Tracker → http://localhost:5050\n")
    app.run(debug=debug, port=5050)
