"""TypeSafe JSON transport using Windows' existing curl/TLS implementation."""

import json
import shutil
import subprocess
from urllib.parse import urlsplit


class TypeSafeHTTPError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"TypeSafe HTTP {status}; no action applied")


def request_json(endpoint, key, timeout, payload=None, proxy=None):
    if endpoint not in ("https://api.typesafe.ai/v1/models",
                        "https://api.typesafe.ai/v1/systemone"):
        raise ValueError("Only the official TypeSafe endpoints are permitted")
    curl = shutil.which("curl.exe")
    if not curl:
        raise RuntimeError("Windows curl.exe is required for TypeSafe HTTPS requests")
    if any(char in key for char in ("\r", "\n", "\0")):
        raise ValueError("Invalid TypeSafe key format")
    proxy_args = []
    if proxy:
        address = urlsplit(proxy)
        if (address.scheme not in ("http", "https", "socks5", "socks5h") or
                address.hostname not in ("127.0.0.1", "localhost", "::1") or
                not address.port or address.username or address.password or
                address.path not in ("", "/") or address.query or address.fragment):
            raise ValueError("The configured TypeSafe proxy must be a local HTTP or SOCKS proxy")
        # Override NO_PROXY so a configured local route cannot silently become
        # a direct request. curl fails the request if the proxy is unavailable.
        proxy_args = ["--proxy", proxy, "--noproxy", ""]
    settings = [f"url = {json.dumps(endpoint)}",
                f"header = {json.dumps('Authorization: Bearer ' + key)}",
                'header = "Accept: application/json"',
                'user-agent = "gta-benchmark/0.1"']
    if payload is not None:
        body = json.dumps(payload, allow_nan=False, separators=(",", ":"))
        settings.extend(['request = "POST"', 'header = "Content-Type: application/json"',
                         f"data-binary = {json.dumps(body, ensure_ascii=False)}"])
    # Authorization and request data travel over stdin, never command-line
    # arguments, temporary files, stderr logs, or a redirect to another host.
    try:
        response = subprocess.run([
            curl, "--disable", "--silent", "--show-error", "--proto", "=https",
            *proxy_args,
            "--max-time", str(timeout), "--connect-timeout", str(min(timeout, 5)),
            "--max-filesize", str(2 * 1024 * 1024), "--write-out", "\n%{http_code}",
            "--config", "-"
        ], input=("\n".join(settings) + "\n").encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout + 1, creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise RuntimeError("TypeSafe request timed out; no action applied") from None
    if response.returncode:
        if response.returncode == 28:
            raise RuntimeError("TypeSafe request timed out (curl code 28); no action applied")
        raise RuntimeError(f"TypeSafe transport failed (curl code {response.returncode}); no action applied")
    body, _, status = response.stdout.rpartition(b"\n")
    if not status.isdigit():
        raise RuntimeError("TypeSafe returned no HTTP status; no action applied")
    if not 200 <= int(status) < 300:
        raise TypeSafeHTTPError(int(status))
    if len(body) > 2 * 1024 * 1024:
        raise RuntimeError("TypeSafe response exceeded the size limit")
    try:
        return json.loads(body)
    except (ValueError, UnicodeError):
        raise RuntimeError("TypeSafe returned invalid JSON; no action applied") from None
