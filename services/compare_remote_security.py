"""远程联邦连接安全校验。"""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _resolve_host_addresses(hostname: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    addresses: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if sockaddr:
            addresses.append(str(sockaddr[0]))
    return addresses


def _is_blocked_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if ip.is_loopback:
        return False
    return bool(
        ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def assert_remote_host_allowed(config: dict[str, Any], base_url: str) -> None:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("远程地址缺少主机名")

    allow_private = _truthy(config.get("FEDERATION_ALLOW_PRIVATE_HOSTS"))
    if not allow_private and host not in _LOCAL_HOSTS:
        for address in _resolve_host_addresses(host):
            if _is_blocked_ip(address):
                raise ValueError(f"远程地址指向内网或保留地址（{address}），已拒绝连接")

    allowed_raw = (config.get("FEDERATION_ALLOWED_HOSTS") or "").strip()
    if allowed_raw:
        allowed_hosts = {item.strip().lower() for item in allowed_raw.split(",") if item.strip()}
        if host not in allowed_hosts:
            raise ValueError(f"远程地址主机不在白名单内：{host}")
