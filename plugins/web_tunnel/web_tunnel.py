"""
AION Plugin: Web Tunnel — Secure External Access
=================================================
Makes the AION Web UI accessible from outside the local network without
relying on any external tunnel service.

How it works:
  1. Generates a self-signed TLS certificate (via `cryptography` or `openssl`)
  2. Starts a second uvicorn server on port 7443 with HTTPS
  3. Generates a random Bearer token and stores it in config.json["web_auth_token"]
  4. Auth middleware in aion_web.py enforces the token on all API endpoints
  5. User forwards port 7443 on their router → HTTPS access from anywhere

Optional: provider="cloudflared" for zero-config public URL (no port forwarding needed).

Tools:
  tunnel_start(provider="https_direct")  — start HTTPS tunnel
  tunnel_stop()                           — stop HTTPS server + clear auth token
  tunnel_status()                         — show current status, URL, token

Configuration:
  config.json["web_auth_token"]   — Bearer token (auto-generated)
  config.json["tunnel_https_port"] — HTTPS port (default 7443)
"""

import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
from pathlib import Path

BOT_DIR = Path(__file__).parent.parent.parent

# ── State ─────────────────────────────────────────────────────────────────────

_https_server_thread: threading.Thread | None = None
_https_server        = None          # uvicorn Server instance
_cloudflared_proc    = None          # subprocess.Popen for cloudflared
_tunnel_url: str     = ""            # active public URL (cloudflared only)


# ── Config helpers ────────────────────────────────────────────────────────────

def _load_cfg() -> dict:
    try:
        import config_store as _cs
        return _cs.load()
    except Exception:
        cfg_file = BOT_DIR / "config.json"
        try:
            return json.loads(cfg_file.read_text(encoding="utf-8")) if cfg_file.is_file() else {}
        except Exception:
            return {}

def _set_cfg(key: str, value) -> None:
    try:
        import config_store as _cs
        _cs.update(key, value)
    except Exception:
        pass


# ── Local IP helper ──────────────────────────────────────────────────────────

def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ── TLS Certificate generation ────────────────────────────────────────────────

def _cert_paths() -> tuple[Path, Path]:
    cert_dir = BOT_DIR / "certs"
    cert_dir.mkdir(exist_ok=True)
    return cert_dir / "aion.crt", cert_dir / "aion.key"


def _generate_cert() -> tuple[Path, Path]:
    """Generate a self-signed TLS certificate. Returns (cert_path, key_path)."""
    cert_path, key_path = _cert_paths()
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path   # reuse existing cert

    # Method 1: cryptography library (preferred)
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AION")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName([
                x509.IPAddress(__import__("ipaddress").IPv4Address("0.0.0.0")),
                x509.DNSName("localhost"),
            ]), critical=False)
            .sign(key, hashes.SHA256())
        )
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))
        return cert_path, key_path
    except ImportError:
        pass

    # Method 2: openssl subprocess fallback
    try:
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key_path), "-out", str(cert_path),
            "-days", "3650", "-nodes",
            "-subj", "/CN=AION",
        ], check=True, capture_output=True)
        return cert_path, key_path
    except Exception as exc:
        raise RuntimeError(f"Cannot generate TLS certificate (install 'cryptography'): {exc}") from exc


# ── HTTPS server ──────────────────────────────────────────────────────────────

def _stop_https():
    global _https_server, _https_server_thread
    if _https_server is not None:
        try:
            _https_server.should_exit = True
        except Exception:
            pass
        _https_server = None
    _https_server_thread = None


def _start_https_server(port: int, cert: Path, key: Path):
    """Start uvicorn HTTPS server in a daemon thread alongside the main HTTP server."""
    global _https_server, _https_server_thread

    _stop_https()

    try:
        import uvicorn
        import aion_web   # import the existing FastAPI app
        cfg = uvicorn.Config(
            aion_web.app,
            host="0.0.0.0",
            port=port,
            ssl_certfile=str(cert),
            ssl_keyfile=str(key),
            log_level="error",
        )
        _https_server = uvicorn.Server(cfg)

        def _run():
            asyncio.run(_https_server.serve())

        _https_server_thread = threading.Thread(target=_run, daemon=True, name="aion-https")
        _https_server_thread.start()
    except Exception as exc:
        raise RuntimeError(f"Failed to start HTTPS server: {exc}") from exc


# ── Cloudflared (optional, external service) ─────────────────────────────────

def _start_cloudflared(http_port: int) -> str:
    """Start cloudflared quick tunnel (no account needed). Returns public URL."""
    global _cloudflared_proc, _tunnel_url

    exe = "cloudflared"
    try:
        subprocess.run([exe, "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise RuntimeError(
            "cloudflared not found. Install from https://github.com/cloudflare/cloudflared/releases "
            "or use provider='https_direct' for no-external-service mode."
        )

    _cloudflared_proc = subprocess.Popen(
        [exe, "tunnel", "--url", f"http://localhost:{http_port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    import re, time
    deadline = time.time() + 20
    while time.time() < deadline:
        line = _cloudflared_proc.stdout.readline()
        if not line:
            break
        m = re.search(r"https://[a-z0-9\-]+\.trycloudflare\.com", line)
        if m:
            _tunnel_url = m.group(0)
            return _tunnel_url
    raise RuntimeError("cloudflared started but no URL detected within 20s.")


def _stop_cloudflared():
    global _cloudflared_proc, _tunnel_url
    if _cloudflared_proc:
        try:
            _cloudflared_proc.terminate()
        except Exception:
            pass
        _cloudflared_proc = None
    _tunnel_url = ""


# ── Tool implementations ──────────────────────────────────────────────────────

def _tunnel_start(provider: str = "https_direct", **_) -> str:
    cfg = _load_cfg()
    http_port  = int(cfg.get("port", os.environ.get("AION_PORT", 7000)))
    https_port = int(cfg.get("tunnel_https_port", 7443))

    # Generate / reuse auth token
    token = cfg.get("web_auth_token", "").strip()
    if not token:
        token = secrets.token_urlsafe(24)
        _set_cfg("web_auth_token", token)

    if provider == "cloudflared":
        # External service (no port forwarding needed)
        url = _start_cloudflared(http_port)
        return (
            f"✓ Cloudflared tunnel active\n"
            f"  URL:   {url}\n"
            f"  Token: {token}\n\n"
            f"Connect: set header  Authorization: Bearer {token}\n"
            f"Or open: {url}?token={token}  (token will be shown in the UI)"
        )

    # Default: HTTPS direct (self-signed cert, no external service)
    try:
        cert, key = _generate_cert()
    except RuntimeError as exc:
        return f"✗ Certificate generation failed: {exc}"

    try:
        _start_https_server(https_port, cert, key)
    except RuntimeError as exc:
        return f"✗ HTTPS server failed: {exc}"

    ip = _local_ip()
    return (
        f"✓ HTTPS server started on port {https_port}\n\n"
        f"  Local URL:  https://{ip}:{https_port}\n"
        f"  Auth Token: {token}\n\n"
        f"  To access from outside:\n"
        f"  1. Forward port {https_port} (TCP) on your router to this machine ({ip})\n"
        f"  2. Open  https://<your-public-ip>:{https_port}  in your browser\n"
        f"  3. Add header  Authorization: Bearer {token}  (or use the Web UI login)\n\n"
        f"  Note: Browser will warn about self-signed certificate — click 'Advanced → Accept'.\n"
        f"  To generate a trusted cert, point a domain to your IP and use Let's Encrypt."
    )


def _tunnel_stop(**_) -> str:
    _stop_https()
    _stop_cloudflared()
    _set_cfg("web_auth_token", "")
    return "✓ Tunnel stopped. Auth token cleared — Web UI is accessible without token again."


def _tunnel_status(**_) -> str:
    cfg    = _load_cfg()
    token  = cfg.get("web_auth_token", "").strip()
    port   = int(cfg.get("tunnel_https_port", 7443))
    active = _https_server_thread is not None and _https_server_thread.is_alive()
    cf_active = _cloudflared_proc is not None and _cloudflared_proc.poll() is None

    lines = ["=== Tunnel Status ==="]
    if cf_active:
        lines.append(f"  Provider:  cloudflared (external)")
        lines.append(f"  URL:       {_tunnel_url or '(detecting…)'}")
    elif active:
        ip = _local_ip()
        lines.append(f"  Provider:  https_direct (self-signed cert)")
        lines.append(f"  Local URL: https://{ip}:{port}")
    else:
        lines.append("  Status:    not running")

    if token:
        lines.append(f"  Auth:      Bearer {token}")
    else:
        lines.append("  Auth:      disabled (no token set)")

    return "\n".join(lines)


# ── Plugin registration ───────────────────────────────────────────────────────

def register(api):
    api.register_tool(
        name="tunnel_start",
        description=(
            "Start secure external access to the AION Web UI. "
            "provider='https_direct' (default): generates self-signed HTTPS cert on port 7443 — "
            "user must forward that port on their router. No external service required. "
            "provider='cloudflared': uses free trycloudflare.com tunnel (no account, no port forwarding). "
            "Automatically sets a Bearer token in config.json for authentication."
        ),
        func=_tunnel_start,
        input_schema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["https_direct", "cloudflared"],
                    "description": "https_direct = self-hosted HTTPS (default); cloudflared = free external tunnel",
                },
            },
        },
        tier=2,
    )

    api.register_tool(
        name="tunnel_stop",
        description="Stop the active external tunnel and clear the auth token (Web UI becomes open again).",
        func=_tunnel_stop,
        input_schema={"type": "object", "properties": {}},
        tier=2,
    )

    api.register_tool(
        name="tunnel_status",
        description="Show current tunnel status: active provider, URL, auth token.",
        func=_tunnel_status,
        input_schema={"type": "object", "properties": {}},
        tier=2,
    )
