#!/usr/bin/env python3
"""
AION Plugin: Paperless-ngx Dokument-Downloader
===============================================
Lädt Dokumente von Paperless-ngx herunter und speichert sie nach
  paperless/<jahr>/<monat>/<dokumentenname>

Zugangsdaten werden verschlüsselt im AION-Vault gespeichert (Dienst: "paperless").
Format im Vault (Markdown):
  ## Paperless
  - url: http://dein-server:30070
  - token: dein_api_token
  - username: dein_user          (optional, falls kein token)
  - password: dein_passwort      (optional, falls kein token)
  - output_dir: C:\\Users\\dein_user\\Desktop\\paperless

Vor dem ersten Aufruf bitte einmalig speichern:
  credential_write("paperless", "<obiges Format mit deinen Daten>")
"""

import re
import json
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


# ── Vault-Hilfsfunktion ────────────────────────────────────────────────────────

async def _load_creds() -> dict:
    """
    Liest Paperless-Zugangsdaten aus dem AION-Vault (Dienst: 'paperless').
    Gibt ein dict mit den Schlüsseln zurück: url, token, username, password, output_dir.
    Wirft RuntimeError wenn Vault-Eintrag fehlt.
    """
    try:
        from plugins.credentials.credentials import _credential_read
    except ImportError:
        raise RuntimeError(
            "Credentials-Plugin nicht gefunden. "
            "Bitte sicherstellen, dass plugins/credentials/credentials.py vorhanden ist."
        )

    raw = await _credential_read("paperless")
    data = json.loads(raw)

    if "error" in data:
        raise RuntimeError(
            f"Keine Paperless-Zugangsdaten im Vault: {data['error']}\n"
            "Bitte speichere die Daten mit: credential_write('paperless', '...')\n"
            "Format:\n"
            "  ## Paperless\n"
            "  - url: http://dein-server:30070\n"
            "  - token: dein_api_token\n"
            "  - output_dir: C:\\Users\\...\\paperless"
        )

    content = data["content"]
    creds = {}
    for key in ("url", "token", "username", "password", "output_dir"):
        match = re.search(rf"[-*]\s*{key}\s*:\s*(.+)", content, re.IGNORECASE)
        creds[key] = match.group(1).strip() if match else None

    if not creds.get("url"):
        raise RuntimeError("Vault-Eintrag 'paperless' hat kein 'url' Feld.")
    if not creds.get("token") and not (creds.get("username") and creds.get("password")):
        raise RuntimeError(
            "Vault-Eintrag 'paperless' braucht entweder 'token' oder 'username' + 'password'."
        )

    if not creds.get("output_dir"):
        raise RuntimeError(
            "Vault-Eintrag 'paperless' hat kein 'output_dir' Feld.\n"
            "Bitte ergänze: - output_dir: C:\\Users\\dein_user\\Desktop\\paperless"
        )
    return creds


# ── Auth ───────────────────────────────────────────────────────────────────────

def _get_auth_headers(base_url: str, token: str | None, username: str | None, password: str | None) -> dict:
    if token:
        return {"Authorization": f"Token {token}"}
    resp = requests.post(
        f"{base_url}/api/token/",
        json={"username": username, "password": password},
        timeout=15,
    )
    resp.raise_for_status()
    fetched = resp.json().get("token")
    if not fetched:
        raise ValueError("Kein Token in der Antwort erhalten.")
    return {"Authorization": f"Token {fetched}"}


# ── Last-Run ───────────────────────────────────────────────────────────────────

_LAST_RUN_FILE = Path(__file__).parent / ".last_run"


def _load_last_run() -> str | None:
    if _LAST_RUN_FILE.exists():
        return json.loads(_LAST_RUN_FILE.read_text()).get("last_run")
    return None


def _save_last_run():
    _LAST_RUN_FILE.write_text(
        json.dumps({"last_run": datetime.now(timezone.utc).isoformat()})
    )


# ── Download-Logik ─────────────────────────────────────────────────────────────

def _fetch_all_documents(base_url: str, headers: dict, since: str | None) -> list:
    documents = []
    url = f"{base_url}/api/documents/?page_size=100"
    if since:
        url += f"&added__date__gt={since[:10]}"
    while url:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        documents.extend(data.get("results", []))
        url = data.get("next")
    return documents


def _sanitize(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name.strip(". ")[:200]


def _download_one(base_url: str, headers: dict, doc: dict, output_dir: str) -> str:
    doc_id = doc["id"]
    date_str = doc.get("created") or doc.get("added", "")
    try:
        date = datetime.fromisoformat(date_str[:10])
    except (ValueError, TypeError):
        date = datetime(1970, 1, 1)

    year  = str(date.year)
    month = f"{date.month:02d}"
    filename = _sanitize(
        doc.get("archived_file_name")
        or doc.get("original_file_name")
        or f"dokument_{doc_id}.pdf"
    )

    target_dir = Path(output_dir) / year / month
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename

    if target_path.exists():
        return f"[SKIP] {year}/{month}/{filename}"

    resp = requests.get(
        f"{base_url}/api/documents/{doc_id}/download/",
        headers=headers,
        timeout=60,
        stream=True,
    )
    resp.raise_for_status()
    with open(target_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return f"[OK]   {year}/{month}/{filename}"


# ── Tool-Funktion ──────────────────────────────────────────────────────────────

async def _paperless_download(max_workers: int = 5) -> str:
    """
    Lädt neue Dokumente von Paperless-ngx herunter.
    Zugangsdaten werden aus dem AION-Vault (Dienst: 'paperless') gelesen.

    max_workers: Anzahl paralleler Download-Threads (Standard: 5)
    """
    try:
        creds = await _load_creds()
    except RuntimeError as e:
        return json.dumps({"error": str(e)})

    base_url   = creds["url"].rstrip("/")
    output_dir = creds["output_dir"]

    try:
        headers = _get_auth_headers(
            base_url, creds.get("token"), creds.get("username"), creds.get("password")
        )
    except Exception as e:
        return json.dumps({"error": f"Authentifizierung fehlgeschlagen: {e}"})

    last_run  = _load_last_run()
    documents = _fetch_all_documents(base_url, headers, since=last_run)

    if not documents:
        _save_last_run()
        return json.dumps({
            "downloaded": 0, "skipped": 0, "errors": 0,
            "message": "Keine neuen Dokumente gefunden."
        })

    success = errors = skipped = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_download_one, base_url, headers, doc, output_dir): doc
            for doc in documents
        }
        for future in as_completed(futures):
            try:
                result = future.result()
                if "[SKIP]" in result:
                    skipped += 1
                else:
                    success += 1
            except Exception:
                errors += 1

    _save_last_run()
    return json.dumps({
        "downloaded": success,
        "skipped":    skipped,
        "errors":     errors,
        "output_dir": str(Path(output_dir).resolve()),
    })


# ── Plugin-Registrierung ───────────────────────────────────────────────────────

def register(api):
    api.register_tool(
        name="paperless_download",
        description=(
            "Lädt neue Dokumente von Paperless-ngx herunter und speichert sie nach "
            "paperless/<jahr>/<monat>/<dateiname>. "
            "Zugangsdaten (URL, API-Token) werden sicher aus dem AION-Vault gelesen. "
            "Beim ersten Aufruf ohne Vault-Eintrag erhältst du eine Anleitung."
        ),
        func=_paperless_download,
        input_schema={
            "type": "object",
            "properties": {
                "max_workers": {
                    "type":        "integer",
                    "description": "Anzahl paralleler Download-Threads (Standard: 5)",
                    "default":     5,
                },
            },
        },
    )
    print("[Plugin] paperless loaded — vault service: 'paperless'")
