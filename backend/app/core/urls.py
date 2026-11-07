"""Rules for the base URL of a registered website.

The API accepts HTTP and HTTPS only. The stored value is normalized so that
cosmetic differences, such as a trailing slash or a default port, do not
create two rows for one site.
"""

from urllib.parse import urlsplit

_MAX_LENGTH = 2048


def normalize_base_url(value: str) -> str:
    """Return a canonical http(s) URL, or raise ValueError."""
    raw = value.strip()
    if not raw or any(character.isspace() for character in raw):
        raise ValueError("Base URL must be an HTTP or HTTPS URL without spaces")

    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise ValueError("Base URL is not a valid URL") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("Base URL must start with http:// or https://")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Base URL must not include a username or password")
    if parsed.query or parsed.fragment:
        raise ValueError("Base URL must not include a query or fragment")

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Base URL has an invalid port") from exc

    host = parsed.hostname
    if host is None:
        raise ValueError("Base URL must include a host")
    host = host.lower().rstrip(".")
    if not host:
        raise ValueError("Base URL must include a host")
    if ":" in host:
        host = f"[{host}]"

    if port is not None and not _is_default_port(scheme, port):
        host = f"{host}:{port}"

    path = parsed.path.rstrip("/")
    normalized = f"{scheme}://{host}{path}"
    if len(normalized) > _MAX_LENGTH:
        raise ValueError("Base URL must be at most 2048 characters")
    return normalized


def _is_default_port(scheme: str, port: int) -> bool:
    return (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
