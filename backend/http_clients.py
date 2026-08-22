import os
from typing import Any, Dict

import httpx


_EXPLICIT_PROXY_ENV_NAMES = (
    "OUTBOUND_PROXY_URL",
    "HTTPS_OUTBOUND_PROXY",
    "HTTP_OUTBOUND_PROXY",
)


def explicit_proxy() -> str | None:
    for name in _EXPLICIT_PROXY_ENV_NAMES:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return None


def request_kwargs(*, timeout: Any) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "timeout": timeout,
        # Ignore ambient HTTP(S)_PROXY / ALL_PROXY variables from the host or shell.
        "trust_env": False,
    }
    proxy = explicit_proxy()
    if proxy:
        kwargs["proxy"] = proxy
    return kwargs


def sync_client(*, timeout: Any) -> httpx.Client:
    return httpx.Client(**request_kwargs(timeout=timeout))


def async_client(*, timeout: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(**request_kwargs(timeout=timeout))
