from __future__ import annotations
import hashlib
import hmac
import ipaddress
import json
import socket
import re
from pathlib import Path
from urllib.parse import urlsplit

ID_RE = re.compile(r"^[a-f0-9]{16}$")

def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024): h.update(chunk)
    return h.hexdigest()

def valid_id(value: str) -> str:
    if not ID_RE.fullmatch(value): raise ValueError("Invalid identifier")
    return value

def safe_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError("Path outside the campaign directory")
    return path

def origin(url: str) -> str:
    p = urlsplit(url)
    if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
        raise ValueError("Only HTTP(S) URLs without credentials are allowed")
    port = p.port or (443 if p.scheme == "https" else 80)
    host = f"[{p.hostname}]" if ":" in p.hostname else p.hostname.lower()
    return f"{p.scheme}://{host}:{port}"

def check_capture_url(url: str, permitted_origins: set[str], internal_demo_origin: str | None = None) -> None:
    o = origin(url)
    if o not in permitted_origins:
        raise ValueError("Capture origin is not allowed. Configure CAPTURE_ALLOWED_ORIGINS explicitly.")
    p = urlsplit(url)
    # The studio itself must never be a browser automation API target.
    if internal_demo_origin and o == internal_demo_origin:
        if not (p.path == "/demo-app" or p.path.startswith("/demo-assets/")):
            raise ValueError("Only the bundled demo app is capturable on the studio origin")
        return
    # An explicitly configured local staging origin is allowed; metadata/link-local never is.
    try:
        addresses = [ipaddress.ip_address(p.hostname)]
    except ValueError:
        addresses = [ipaddress.ip_address(v[4][0]) for v in socket.getaddrinfo(p.hostname, p.port or 443, type=socket.SOCK_STREAM)]
    for ip in addresses:
        if ip.is_link_local or ip.is_multicast or ip.is_unspecified or str(ip) == "169.254.169.254":
            raise ValueError("Unsafe network destination")

def tracking_token(secret: str, cid: str) -> str:
    return hmac.new(secret.encode(), ("tracking:" + cid).encode(), hashlib.sha256).hexdigest()[:32]

def conversion_secret(secret: str, cid: str) -> str:
    """Signing key for one campaign's server-to-server conversions.

    Derived, not stored: an operator can paste it into their own backend without
    sharing the studio access token, and it dies with the campaign id."""
    return hmac.new(secret.encode(), ("conversion:" + cid).encode(), hashlib.sha256).hexdigest()

def signed_body(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

def scrub_error(error: Exception, secrets: list[str]) -> str:
    text = str(error)
    for secret in secrets:
        if secret: text = text.replace(secret, "[redacted]")
    return text[:800]
