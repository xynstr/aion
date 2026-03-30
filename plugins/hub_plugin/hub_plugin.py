"""
AION Plugin Hub — hub_list / hub_install / hub_remove / hub_update

Manifest-URL kann per Vault-Key HUB_MANIFEST_URL überschrieben werden.
Standard: https://raw.githubusercontent.com/xynstr/aion-hub-plugins/main/manifest.json
"""

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

_DEFAULT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/xynstr/aion-hub-plugins/main/manifest.json"
)
_PLUGINS_DIR = Path(__file__).parent.parent  # .../plugins/


def _manifest_url() -> str:
    try:
        import config_store as _cs
        url = _cs.get_key("HUB_MANIFEST_URL")
        if url:
            return url
    except Exception:
        pass
    return _DEFAULT_MANIFEST_URL


async def _fetch_manifest() -> tuple[dict, str]:
    """Lädt das Manifest. Gibt (manifest_dict, error_str) zurück."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(_manifest_url())
            r.raise_for_status()
            return r.json(), ""
    except Exception as exc:
        return {}, str(exc)


# ---------------------------------------------------------------------------
# hub_list
# ---------------------------------------------------------------------------

async def _hub_list(**_):
    manifest, err = await _fetch_manifest()
    if err:
        return json.dumps({"error": f"Manifest nicht erreichbar: {err}"})

    plugins = []
    for name, info in manifest.items():
        installed = (_PLUGINS_DIR / name / f"{name}.py").exists()
        local_version = None
        if installed:
            vf = _PLUGINS_DIR / name / "version.txt"
            local_version = vf.read_text().strip() if vf.exists() else "?"
        plugins.append({
            "name": name,
            "display_name": info.get("name", name),
            "version": info.get("version", "?"),
            "local_version": local_version,
            "description": info.get("description", ""),
            "dependencies": info.get("dependencies", []),
            "installed": installed,
            "update_available": (
                installed and local_version is not None
                and local_version != info.get("version")
            ),
        })

    return json.dumps({"plugins": plugins, "total": len(plugins)}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# hub_install
# ---------------------------------------------------------------------------

async def _hub_install(plugin_name: str = "", **_):
    import httpx

    if not plugin_name:
        return json.dumps({"error": "plugin_name ist Pflichtfeld."})

    manifest, err = await _fetch_manifest()
    if err:
        return json.dumps({"error": f"Manifest nicht erreichbar: {err}"})

    if plugin_name not in manifest:
        return json.dumps({
            "error": f"Plugin '{plugin_name}' nicht im Manifest.",
            "available": list(manifest.keys()),
        })

    info = manifest[plugin_name]
    download_url = info.get("download_url")
    expected_sha256 = info.get("sha256")

    if not download_url:
        return json.dumps({"error": f"Kein download_url für '{plugin_name}' im Manifest."})

    # 1. Download
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            r = await client.get(download_url)
            r.raise_for_status()
            zip_bytes = r.content
    except Exception as exc:
        return json.dumps({"error": f"Download fehlgeschlagen: {exc}"})

    # 2. SHA256-Check
    if expected_sha256:
        actual = hashlib.sha256(zip_bytes).hexdigest()
        if actual != expected_sha256:
            return json.dumps({
                "error": "SHA256-Hash stimmt nicht überein — Download abgebrochen.",
                "expected": expected_sha256,
                "actual": actual,
            })

    # 3. Snapshot des bestehenden Plugins
    plugin_dir = _PLUGINS_DIR / plugin_name
    from plugin_loader import create_snapshot
    snapshot = create_snapshot(plugin_name) if plugin_dir.exists() else None

    # 4. ZIP entpacken
    import tempfile
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / f"{plugin_name}.zip"
            tmp_path.write_bytes(zip_bytes)

            with zipfile.ZipFile(tmp_path) as zf:
                names = zf.namelist()
                prefix = plugin_name + "/"
                # ZIP hat plugin_name/ als Root-Ordner → in Parent entpacken
                if all(n == prefix or n.startswith(prefix) for n in names):
                    zf.extractall(tmpdir)
                    extracted = Path(tmpdir) / plugin_name
                else:
                    # Kein Root-Ordner → direkt in plugin_name/ entpacken
                    extracted = Path(tmpdir) / plugin_name
                    extracted.mkdir()
                    zf.extractall(extracted)

                if plugin_dir.exists():
                    shutil.rmtree(plugin_dir)
                shutil.copytree(extracted, plugin_dir)
    except Exception as exc:
        return json.dumps({"error": f"Entpacken fehlgeschlagen: {exc}"})

    # 5. Version festhalten
    (plugin_dir / "version.txt").write_text(info.get("version", "?"), encoding="utf-8")

    # 6. Dependencies installieren
    pip_log = None
    req_file = plugin_dir / "requirements.txt"
    deps = info.get("dependencies", [])
    if req_file.exists():
        pip_args = [sys.executable, "-m", "pip", "install", "-r", str(req_file), "-q"]
    elif deps:
        pip_args = [sys.executable, "-m", "pip", "install", "-q"] + deps
    else:
        pip_args = None

    if pip_args:
        try:
            proc = subprocess.run(pip_args, capture_output=True, text=True, timeout=120)
            pip_log = "ok" if proc.returncode == 0 else proc.stderr[:400]
        except Exception as exc:
            pip_log = f"pip fehlgeschlagen: {exc}"

    # 7. Hot-Reload
    try:
        import aion as _aion_mod
        from plugin_loader import load_plugins
        load_plugins(_aion_mod._plugin_tools)
        reloaded = True
    except Exception as exc:
        reloaded = False
        pip_log = (pip_log or "") + f" | reload-error: {exc}"

    return json.dumps({
        "ok": True,
        "plugin": plugin_name,
        "version": info.get("version", "?"),
        "snapshot": snapshot,
        "pip": pip_log,
        "reloaded": reloaded,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# hub_remove
# ---------------------------------------------------------------------------

async def _hub_remove(plugin_name: str = "", **_):
    if not plugin_name:
        return json.dumps({"error": "plugin_name ist Pflichtfeld."})

    plugin_dir = _PLUGINS_DIR / plugin_name
    if not plugin_dir.exists():
        return json.dumps({"error": f"Plugin '{plugin_name}' ist nicht installiert."})

    from plugin_loader import create_snapshot, load_plugins
    snapshot = create_snapshot(plugin_name)
    shutil.rmtree(plugin_dir)

    import aion as _aion_mod
    load_plugins(_aion_mod._plugin_tools)

    return json.dumps({
        "ok": True,
        "removed": plugin_name,
        "snapshot": snapshot,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# hub_update
# ---------------------------------------------------------------------------

async def _hub_update(plugin_name: str = "", **_):
    manifest, err = await _fetch_manifest()
    if err:
        return json.dumps({"error": f"Manifest nicht erreichbar: {err}"})

    if plugin_name:
        return await _hub_install(plugin_name)

    # Alle installierten Plugins auf Updates prüfen
    updates = []
    for name, info in manifest.items():
        vf = _PLUGINS_DIR / name / "version.txt"
        if not (_PLUGINS_DIR / name / f"{name}.py").exists():
            continue
        local = vf.read_text().strip() if vf.exists() else None
        remote = info.get("version", "?")
        if local != remote:
            updates.append({"name": name, "local": local or "?", "remote": remote})

    if not updates:
        return json.dumps({"ok": True, "message": "Alle Plugins sind aktuell."})

    return json.dumps({"updates_available": updates}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

def register(api):
    api.register_tool(
        "hub_list",
        "Zeigt alle Plugins im AION Plugin-Hub mit Version und ob sie installiert sind.",
        _hub_list,
        {"type": "object", "properties": {}},
        tier=2,
    )
    api.register_tool(
        "hub_install",
        "Installiert ein Plugin aus dem AION Hub: lädt ZIP herunter, prüft SHA256, entpackt, installiert Dependencies, Hot-Reload.",
        _hub_install,
        {
            "type": "object",
            "properties": {
                "plugin_name": {
                    "type": "string",
                    "description": "Name des Plugins (aus hub_list)",
                },
            },
            "required": ["plugin_name"],
        },
        tier=2,
    )
    api.register_tool(
        "hub_remove",
        "Entfernt ein installiertes Plugin (Snapshot-Backup wird angelegt). Hot-Reload danach.",
        _hub_remove,
        {
            "type": "object",
            "properties": {
                "plugin_name": {
                    "type": "string",
                    "description": "Name des zu entfernenden Plugins",
                },
            },
            "required": ["plugin_name"],
        },
        tier=2,
    )
    api.register_tool(
        "hub_update",
        "Prüft ob Updates verfügbar sind. Mit plugin_name: updatet nur dieses Plugin. Ohne: zeigt welche Updates ausstehen.",
        _hub_update,
        {
            "type": "object",
            "properties": {
                "plugin_name": {
                    "type": "string",
                    "description": "Optional: nur dieses Plugin updaten",
                },
            },
        },
        tier=2,
    )
