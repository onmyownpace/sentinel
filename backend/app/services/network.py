"""Public-address policy for website checks.

Registration may store a local URL. A check may not open one. Every HTTP and
HTTPS target is resolved, and any address that is not a public unicast address
is rejected. The same rule is applied to the final URL and to browser requests.
"""

import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable, Sequence
from urllib.parse import urlsplit

Address = ipaddress.IPv4Address | ipaddress.IPv6Address
ResolveHost = Callable[[str, int], Awaitable[Sequence[Address]]]

UNSAFE_TARGET = (
    "This website cannot be checked because its address is not a public HTTP or HTTPS site."
)
UNRESOLVED_HOST = "The host name could not be resolved."
BLOCKED_REQUEST = "Blocked because the address is not public."

_BLOCKED_NAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata",
        "metadata.google.internal",
        "metadata.goog",
        "instance-data",
    }
)
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain")
_DOTTED_QUAD = re.compile(r"^\d+\.\d+\.\d+\.\d+$")


class TargetNotAllowed(Exception):
    """The URL must not be opened by the browser check."""

    def __init__(self, message: str = UNSAFE_TARGET) -> None:
        super().__init__(message)
        self.message = message


async def ensure_public_http_url(url: str, *, resolve: ResolveHost | None = None) -> None:
    """Raise TargetNotAllowed unless every address behind `url` is public HTTP(S)."""
    try:
        parsed = urlsplit(url.strip())
    except ValueError as exc:
        raise TargetNotAllowed() from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or parsed.username is not None or parsed.password is not None:
        raise TargetNotAllowed()

    host = parsed.hostname
    if host is None:
        raise TargetNotAllowed()
    host = host.lower().rstrip(".")
    if not host or _name_is_blocked(host):
        raise TargetNotAllowed()

    try:
        port = parsed.port
    except ValueError as exc:
        raise TargetNotAllowed() from exc
    if port is None:
        port = 443 if scheme == "https" else 80
    if port == 0:
        raise TargetNotAllowed()

    literal = _literal_address(host)
    if literal is not None:
        if not _is_public(literal):
            raise TargetNotAllowed()
        return

    resolver = resolve or resolve_host_addresses
    try:
        addresses = list(await resolver(host, port))
    except OSError as exc:
        raise TargetNotAllowed(UNRESOLVED_HOST) from exc
    if not addresses or any(not _is_public(address) for address in addresses):
        raise TargetNotAllowed()


async def classify_browser_url(url: str, *, resolve: ResolveHost | None = None) -> str:
    """Return `skip` for data or blob URLs, `allow` for public HTTP(S), otherwise `block`."""
    try:
        scheme = urlsplit(url.strip()).scheme.lower()
    except ValueError:
        return "block"
    if scheme in {"data", "blob"}:
        return "skip"
    try:
        await ensure_public_http_url(url, resolve=resolve)
    except TargetNotAllowed:
        return "block"
    return "allow"


async def resolve_host_addresses(host: str, port: int) -> list[Address]:
    """Resolve `host` with the system resolver. Callers decide which answers are public."""
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise OSError("unresolved") from exc

    addresses: list[Address] = []
    for *_, sockaddr in infos:
        addresses.append(ipaddress.ip_address(sockaddr[0]))
    return addresses


def _name_is_blocked(host: str) -> bool:
    if host in _BLOCKED_NAMES or host.endswith(_BLOCKED_SUFFIXES):
        return True
    if host.isdigit():
        return True
    return any(label.startswith("0x") for label in host.split("."))


def _literal_address(host: str) -> Address | None:
    if _DOTTED_QUAD.fullmatch(host):
        try:
            return ipaddress.IPv4Address(host)
        except ValueError as exc:
            raise TargetNotAllowed() from exc
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _is_public(ip: Address) -> bool:
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return _is_public(mapped)
    if (
        ip.is_multicast
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    ):
        return False
    return True
