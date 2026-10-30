"""
Ponfolio — Google OAuth + Google Drive Sync
Handles Google Sign-In for desktop app and Drive data backup/restore.
"""
import os
import hashlib
import json
import time
import urllib.parse
import http.server
import threading
import webbrowser
from pathlib import Path

import httpx

# ── Google OAuth Config ──
# The OAuth client is not stored in source. It is read, first match wins, from
#   1. GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET environment variables
#   2. backend/google_oauth.json (git-ignored; bundled by the installer if present)
#   3. backend/data/google_oauth.json (per-install runtime data)
# as {"client_id": "...", "client_secret": "..."}. Without one, sign-in is disabled.
def _load_oauth_client():
    cid = os.environ.get("GOOGLE_CLIENT_ID", "")
    secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    if cid and secret:
        return cid, secret
    here = Path(__file__).parent
    for path in (here / "google_oauth.json", here / "data" / "google_oauth.json"):
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
            return cfg.get("client_id", ""), cfg.get("client_secret", "")
        except (OSError, ValueError):
            continue
    return "", ""


GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET = _load_oauth_client()
REDIRECT_URI = "http://localhost:8183/callback"
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/drive.appdata",
]

DATA_DIR = Path(__file__).parent / "data"
AUTH_FILE = DATA_DIR / "auth.json"

# ── Token Storage ──
def load_auth():
    """Load saved auth tokens and profile."""
    if AUTH_FILE.exists():
        try:
            return json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def save_auth(data):
    """Save auth tokens and profile."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def clear_auth():
    """Remove auth data (logout)."""
    if AUTH_FILE.exists():
        AUTH_FILE.unlink()

def get_profile():
    """Get current user profile or None."""
    auth = load_auth()
    if not auth:
        return None
    # Check if token is expired
    if auth.get("expires_at", 0) < time.time():
        # Try refresh
        refreshed = refresh_token(auth.get("refresh_token"))
        if refreshed:
            auth.update(refreshed)
            save_auth(auth)
        else:
            return None
    return {
        "name": auth.get("name", ""),
        "email": auth.get("email", ""),
        "picture": auth.get("picture", ""),
        "logged_in": True,
    }

# ── OAuth Flow ──
def get_auth_url():
    """Generate Google OAuth URL."""
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"

def exchange_code(code: str):
    """Exchange auth code for tokens."""
    try:
        resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            tokens = resp.json()
            # Get user profile
            profile = get_user_info(tokens["access_token"])
            auth_data = {
                "access_token": tokens["access_token"],
                "refresh_token": tokens.get("refresh_token", ""),
                "expires_at": time.time() + tokens.get("expires_in", 3600),
                "name": profile.get("name", ""),
                "email": profile.get("email", ""),
                "picture": profile.get("picture", ""),
            }
            save_auth(auth_data)
            return auth_data
        else:
            print(f"[Auth] Token exchange failed: {resp.status_code} {resp.text}")
            return None
    except Exception as e:
        print(f"[Auth] Token exchange error: {e}")
        return None

def refresh_token(refresh_tok: str):
    """Refresh an expired access token."""
    if not refresh_tok:
        return None
    try:
        resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "refresh_token": refresh_tok,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "grant_type": "refresh_token",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {
                "access_token": data["access_token"],
                "expires_at": time.time() + data.get("expires_in", 3600),
            }
    except Exception as e:
        print(f"[Auth] Refresh error: {e}")
    return None

def get_user_info(access_token: str):
    """Fetch Google user profile."""
    try:
        resp = httpx.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"[Auth] User info error: {e}")
    return {}

# ── OAuth Callback Server ──
_auth_code_result = {"code": None, "error": None}

class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handles the OAuth redirect callback."""
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            code = params["code"][0]
            _auth_code_result["code"] = code
            # Auto-exchange code for tokens so profile polling detects login
            try:
                result = exchange_code(code)
                if result:
                    print(f"[Auth] Login successful: {result.get('name', '')} ({result.get('email', '')})")
                else:
                    print("[Auth] Code exchange failed")
            except Exception as e:
                print(f"[Auth] Auto-exchange error: {e}")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
            <html><body style="background:#0a0e1a;color:#fff;font-family:Inter,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
            <div style="text-align:center;">
                <div style="font-size:60px;margin-bottom:20px;">&#10004;</div>
                <h1 style="color:#10b981;">Login Successful!</h1>
                <p style="color:#9ca3af;">You can close this window and return to Ponfolio.</p>
            </div>
            </body></html>
            """)
        else:
            _auth_code_result["error"] = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Login Failed</h1></body></html>")
    
    def log_message(self, format, *args):
        pass  # Suppress logs

def start_callback_server():
    """Start a temporary HTTP server to catch the OAuth callback."""
    _auth_code_result["code"] = None
    _auth_code_result["error"] = None
    server = http.server.HTTPServer(("localhost", 8183), OAuthCallbackHandler)
    server.timeout = 120  # 2 min timeout
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    return server, thread

# ── Google Drive Sync ──
DRIVE_FOLDER_NAME = "Ponfolio_Data"
SYNC_FILES = ["portfolio.json", "mf_portfolio.json", "watchlist.json", "settings.json",
              "swing_daily_picks.json", "swing_desk.json", "swing_paper.json",
              # The imported Kite P&L statements travel with the ledger they
              # reconcile against. Syncing one without the other would leave a
              # second machine showing estimated charges for trades whose real
              # ones are already on record.
              "equity_txns.json", "equity_pnl.json", "equity_ledger.json",
              "deploy_log.json",
              # Theses, sell triggers and quarterly snapshots: the user's own
              # reasoning, which must follow them to every machine.
              "conviction.json"]

# Serialize uploads: concurrent "check-then-create" calls used to race and
# produce duplicate copies of the same file on Drive.
_upload_lock = threading.Lock()

def _get_access_token():
    """Get a valid access token."""
    auth = load_auth()
    if not auth:
        return None
    if auth.get("expires_at", 0) < time.time():
        refreshed = refresh_token(auth.get("refresh_token"))
        if refreshed:
            auth.update(refreshed)
            save_auth(auth)
        else:
            return None
    return auth.get("access_token")

def _drive_headers():
    token = _get_access_token()
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}

def drive_find_or_create_folder():
    """Find or create the app data folder in Drive appDataFolder."""
    headers = _drive_headers()
    if not headers:
        return None
    try:
        # Search for existing folder
        resp = httpx.get(
            "https://www.googleapis.com/drive/v3/files",
            params={
                "q": f"name='{DRIVE_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and 'appDataFolder' in parents and trashed=false",
                "spaces": "appDataFolder",
                "fields": "files(id,name)",
            },
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 200:
            files = resp.json().get("files", [])
            if files:
                return files[0]["id"]
        # Create folder
        resp = httpx.post(
            "https://www.googleapis.com/drive/v3/files",
            json={
                "name": DRIVE_FOLDER_NAME,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": ["appDataFolder"],
            },
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()["id"]
    except Exception as e:
        print(f"[Drive] Folder error: {e}")
    return None

def drive_delete_file(file_id: str) -> bool:
    """Delete a Drive file by id. Returns True on success."""
    headers = _drive_headers()
    if not headers or not file_id:
        return False
    try:
        resp = httpx.delete(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            headers=headers,
            timeout=15,
        )
        return resp.status_code in (200, 204)
    except Exception as e:
        print(f"[Drive] Delete error ({file_id}): {e}")
        return False

# What drive_sync_file reports. UNCHANGED counts as success: Drive already
# holds exactly these bytes.
SYNC_CREATED = "created"
SYNC_UPDATED = "updated"
SYNC_UNCHANGED = "unchanged"
SYNC_FAILED = "failed"


def drive_upload_file(filename: str, data_dir: Path = None):
    """Upload a data file to Google Drive. True when Drive holds the file.

    See drive_sync_file; this is the boolean form existing callers use.
    """
    return drive_sync_file(filename, data_dir) in (
        SYNC_CREATED, SYNC_UPDATED, SYNC_UNCHANGED)


def drive_sync_file(filename: str, data_dir: Path = None) -> str:
    """Upload a data file to Google Drive, unless Drive already has it.

    Serialized via a lock and de-duplicating: updates the NEWEST existing copy
    and deletes any older duplicates, so a file only ever has one copy on Drive.

    Content-addressed: every save used to PATCH the file whether or not a byte
    had changed, and each PATCH is a new Drive revision — a Kite sync that
    rewrote an identical portfolio.json, or a no-change expense save, piled up
    "new version" after "new version". Drive reports an md5 for every uploaded
    file, so identical bytes are now recognised and nothing is sent.
    """
    headers = _drive_headers()
    if not headers:
        return SYNC_FAILED
    filepath = (data_dir or DATA_DIR) / filename
    if not filepath.exists():
        return SYNC_FAILED
    with _upload_lock:
        try:
            folder_id = drive_find_or_create_folder()
            if not folder_id:
                return False
            # Find existing copies, newest first
            resp = httpx.get(
                "https://www.googleapis.com/drive/v3/files",
                params={
                    "q": f"name='{filename}' and '{folder_id}' in parents and trashed=false",
                    "spaces": "appDataFolder",
                    "fields": "files(id,name,modifiedTime,md5Checksum)",
                    "orderBy": "modifiedTime desc",
                },
                headers=headers,
                timeout=15,
            )
            existing_id = None
            existing_md5 = None
            stale_ids = []
            if resp.status_code == 200:
                files = resp.json().get("files", [])
                if files:
                    existing_id = files[0]["id"]
                    existing_md5 = files[0].get("md5Checksum")
                    stale_ids = [f["id"] for f in files[1:]]  # older duplicates
            content = filepath.read_bytes()
            # Clean up any older duplicates left by past race conditions
            for sid in stale_ids:
                drive_delete_file(sid)
            if existing_id and existing_md5 and                     existing_md5 == hashlib.md5(content).hexdigest():
                return SYNC_UNCHANGED
            if existing_id:
                # Update existing
                resp = httpx.patch(
                    f"https://www.googleapis.com/upload/drive/v3/files/{existing_id}",
                    params={"uploadType": "media"},
                    content=content,
                    headers={**headers, "Content-Type": "application/json"},
                    timeout=15,
                )
            else:
                # Create new
                metadata = json.dumps({"name": filename, "parents": [folder_id]})
                boundary = "aiei_wealth_boundary"
                body = (
                    f"--{boundary}\r\n"
                    f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                    f"{metadata}\r\n"
                    f"--{boundary}\r\n"
                    f"Content-Type: application/json\r\n\r\n"
                ).encode() + content + f"\r\n--{boundary}--".encode()
                resp = httpx.post(
                    "https://www.googleapis.com/upload/drive/v3/files",
                    params={"uploadType": "multipart"},
                    content=body,
                    headers={**headers, "Content-Type": f"multipart/related; boundary={boundary}"},
                    timeout=15,
                )
            if resp.status_code not in (200, 201):
                return SYNC_FAILED
            return SYNC_UPDATED if existing_id else SYNC_CREATED
        except Exception as e:
            print(f"[Drive] Upload error ({filename}): {e}")
            return SYNC_FAILED

def drive_download_file(filename: str, data_dir: Path = None):
    """Download a data file from Google Drive (newest copy if duplicates exist)."""
    headers = _drive_headers()
    if not headers:
        return False
    try:
        folder_id = drive_find_or_create_folder()
        if not folder_id:
            return False
        resp = httpx.get(
            "https://www.googleapis.com/drive/v3/files",
            params={
                "q": f"name='{filename}' and '{folder_id}' in parents and trashed=false",
                "spaces": "appDataFolder",
                "fields": "files(id,name,modifiedTime)",
                "orderBy": "modifiedTime desc",
            },
            headers=headers,
            timeout=15,
        )
        if resp.status_code != 200:
            return False
        files = resp.json().get("files", [])
        if not files:
            return False
        file_id = files[0]["id"]
        resp = httpx.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            params={"alt": "media"},
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 200:
            target_dir = data_dir or DATA_DIR
            target_dir.mkdir(parents=True, exist_ok=True)
            filepath = target_dir / filename
            filepath.write_bytes(resp.content)
            return True
    except Exception as e:
        print(f"[Drive] Download error ({filename}): {e}")
    return False

def drive_sync_all(direction="upload", data_dir: Path = None):
    """Sync all data files to/from Drive."""
    results = {}
    for f in SYNC_FILES:
        if direction == "upload":
            results[f] = drive_upload_file(f, data_dir)
        else:
            results[f] = drive_download_file(f, data_dir)
    return results

def _drive_mtime_epoch(modified_time: str):
    """Parse a Drive RFC3339 modifiedTime (e.g. '2026-07-13T02:26:41.956Z') to epoch seconds, or None."""
    if not modified_time:
        return None
    try:
        from datetime import datetime
        # Python 3.11+ handles the trailing 'Z'; fall back to manual replace otherwise.
        try:
            dt = datetime.fromisoformat(modified_time)
        except ValueError:
            dt = datetime.fromisoformat(modified_time.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return None

def drive_pull_newer(data_dir: Path = None):
    """Download each sync file ONLY when Drive's copy is newer than the local one
    (or the local file is missing). Prevents clobbering unsynced local edits.
    Returns {filename: True} for files actually pulled."""
    results = {}
    target_dir = data_dir or DATA_DIR
    # drive_list_files() is newest-first; keep the newest copy per name.
    remote = {}
    for f in drive_list_files():
        remote.setdefault(f.get("name"), f)
    for name in SYNC_FILES:
        meta = remote.get(name)
        if not meta:
            continue  # not on Drive yet
        drive_mtime = _drive_mtime_epoch(meta.get("modifiedTime"))
        local = target_dir / name
        local_mtime = local.stat().st_mtime if local.exists() else 0
        # 2s skew tolerance so a file we just uploaded isn't re-downloaded.
        if drive_mtime and drive_mtime > local_mtime + 2:
            if drive_download_file(name, data_dir):
                results[name] = True
    return results

def drive_list_files(prefix: str = None):
    """List files in the app-data folder, optionally filtered by name prefix.
    Returns [{id, name, modifiedTime, size}] newest-first, or [] if not authed."""
    headers = _drive_headers()
    if not headers:
        return []
    try:
        folder_id = drive_find_or_create_folder()
        if not folder_id:
            return []
        resp = httpx.get(
            "https://www.googleapis.com/drive/v3/files",
            params={
                "q": f"'{folder_id}' in parents and trashed=false",
                "spaces": "appDataFolder",
                "fields": "files(id,name,modifiedTime,size)",
                "orderBy": "modifiedTime desc",
                "pageSize": 200,
            },
            headers=headers,
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        files = resp.json().get("files", [])
        if prefix:
            files = [f for f in files if f.get("name", "").startswith(prefix)]
        return files
    except Exception as e:
        print(f"[Drive] List error: {e}")
        return []

def drive_get_content(filename: str):
    """Return the raw bytes of a Drive file by name (newest copy), or None."""
    headers = _drive_headers()
    if not headers:
        return None
    try:
        folder_id = drive_find_or_create_folder()
        if not folder_id:
            return None
        resp = httpx.get(
            "https://www.googleapis.com/drive/v3/files",
            params={
                "q": f"name='{filename}' and '{folder_id}' in parents and trashed=false",
                "spaces": "appDataFolder",
                "fields": "files(id,name,modifiedTime)",
                "orderBy": "modifiedTime desc",
            },
            headers=headers,
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        files = resp.json().get("files", [])
        if not files:
            return None
        resp = httpx.get(
            f"https://www.googleapis.com/drive/v3/files/{files[0]['id']}",
            params={"alt": "media"},
            headers=headers,
            timeout=20,
        )
        return resp.content if resp.status_code == 200 else None
    except Exception as e:
        print(f"[Drive] Get content error ({filename}): {e}")
        return None

def drive_folder_meta(filename: str):
    """Return {name, modifiedTime, size} for one Drive file, or None."""
    files = drive_list_files()
    for f in files:
        if f.get("name") == filename:
            return f
    return None
