"""
build_release.py — AION Plugin Hub Build Script

Aufruf: python scripts/build_release.py v1.2.0

Was es tut:
  1. Findet alle Plugin-Unterordner (jeder mit plugin_name/plugin_name.py)
  2. Erstellt dist/plugin_name-vX.Y.Z.zip (Root-Ordner = plugin_name/)
  3. Berechnet SHA256-Hash jeder ZIP
  4. Aktualisiert manifest.json mit version, download_url, sha256
  5. Schreibt dist/manifest.json (wird als Release-Asset hochgeladen)
     UND überschreibt die Wurzel-manifest.json (wird committed → raw.githubusercontent.com)
"""

import hashlib
import json
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DIST_DIR  = REPO_ROOT / "dist"
GITHUB_REPO = "xynstr/aion-hub-plugins"   # ← hier anpassen


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def find_plugins() -> list[Path]:
    """Gibt alle Plugin-Verzeichnisse zurück (Unterordner mit plugin_name.py)."""
    plugins = []
    for d in sorted(REPO_ROOT.iterdir()):
        if not d.is_dir():
            continue
        if d.name.startswith(".") or d.name.startswith("_"):
            continue
        if d.name in ("dist", "scripts"):
            continue
        if (d / f"{d.name}.py").exists():
            plugins.append(d)
    return plugins


def read_plugin_meta(plugin_dir: Path) -> dict:
    """Liest plugin.json für Name, Beschreibung und Dependencies."""
    meta_file = plugin_dir / "plugin.json"
    if meta_file.exists():
        try:
            return json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Fallback: README erste Zeile als Beschreibung
    readme = plugin_dir / "README.md"
    description = ""
    if readme.exists():
        for line in readme.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                description = stripped
                break
    return {"name": plugin_dir.name, "description": description, "dependencies": []}


def build_zip(plugin_dir: Path, version: str) -> Path:
    """Packt den Plugin-Ordner als ZIP (Root = plugin_name/)."""
    DIST_DIR.mkdir(exist_ok=True)
    zip_path = DIST_DIR / f"{plugin_dir.name}-{version}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(plugin_dir.rglob("*")):
            if file.is_file():
                # __pycache__ und .pyc überspringen
                if "__pycache__" in file.parts or file.suffix == ".pyc":
                    continue
                arcname = plugin_dir.name + "/" + file.relative_to(plugin_dir).as_posix()
                zf.write(file, arcname)

    return zip_path


def main():
    if len(sys.argv) < 2:
        print("Verwendung: python scripts/build_release.py <version-tag>")
        print("Beispiel:   python scripts/build_release.py v1.2.0")
        sys.exit(1)

    version = sys.argv[1].lstrip("v")   # "v1.2.0" → "1.2.0"
    tag     = f"v{version}"

    plugins = find_plugins()
    if not plugins:
        print("Keine Plugins gefunden.")
        sys.exit(1)

    print(f"Version: {tag} — {len(plugins)} Plugin(s) gefunden\n")

    # Vorhandenes Manifest laden (um bestehende Einträge nicht zu verlieren)
    manifest_path = REPO_ROOT / "manifest.json"
    manifest: dict = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    for plugin_dir in plugins:
        name = plugin_dir.name
        meta = read_plugin_meta(plugin_dir)

        print(f"  📦  {name} …", end=" ", flush=True)
        zip_path = build_zip(plugin_dir, tag)
        digest   = sha256_of(zip_path)

        download_url = (
            f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/{zip_path.name}"
        )

        manifest[name] = {
            "name":         meta.get("name", name),
            "description":  meta.get("description", ""),
            "version":      version,
            "download_url": download_url,
            "sha256":       digest,
            "dependencies": meta.get("dependencies", []),
        }

        print(f"ok  ({zip_path.stat().st_size // 1024} KB)  sha256={digest[:12]}…")

    # manifest.json schreiben — einmal im dist/ (als Release-Asset)
    # und einmal im Repo-Root (wird committed → raw.githubusercontent.com URL)
    manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    manifest_path.write_text(manifest_json, encoding="utf-8")
    (DIST_DIR / "manifest.json").write_text(manifest_json, encoding="utf-8")

    print(f"\n✅  manifest.json aktualisiert ({len(manifest)} Einträge)")
    print(f"📂  Ausgabe: {DIST_DIR}")


if __name__ == "__main__":
    main()
