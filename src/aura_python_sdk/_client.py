"""The AuraClient and AsyncAuraClient entry points (Go: client.go)."""

from __future__ import annotations

import inspect
import logging
import os
from collections.abc import Mapping
from types import TracebackType
from typing import Self

from aura_python_sdk._config import (
    API_VERSION,
    DEFAULT_BASE_URL,
    DEFAULT_MAX_RESPONSE_SIZE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
    ClientConfig,
    build_config,
)
from aura_python_sdk._errors import AuraConfigurationError
from aura_python_sdk._internal._auth import AsyncTokenManager, TokenManager
from aura_python_sdk._internal._request import AsyncRequestService, RequestService
from aura_python_sdk._internal.http._httpx import AsyncHttpxTransport, HttpxTransport
from aura_python_sdk._internal.http._service import AsyncHttpService, HttpService
from aura_python_sdk._transport import AsyncHttpTransport, HttpTransport
from aura_python_sdk.services import (
    AsyncCMEKService,
    AsyncGDSSessionService,
    AsyncInstanceService,
    AsyncPrometheusService,
    AsyncSnapshotService,
    AsyncTenantService,
    CMEKService,
    GDSSessionService,
    InstanceService,
    PrometheusService,
    SnapshotService,
    TenantService,
)

ENV_CLIENT_ID = "AURA_CLIENT_ID"
ENV_CLIENT_SECRET = "AURA_CLIENT_SECRET"  # noqa: S105 - environment variable name, not a secret

_LOGGER_NAME = "aura_python_sdk"


def _resolve_logger(logger: logging.Logger | None) -> logging.Logger:
    if logger is not None and not isinstance(logger, logging.Logger):
        raise AuraConfigurationError("logger must be a logging.Logger")
    return logger or logging.getLogger(_LOGGER_NAME)


def _env_credentials() -> tuple[str, str]:
    client_id = os.environ.get(ENV_CLIENT_ID, "")
    client_secret = os.environ.get(ENV_CLIENT_SECRET, "")
    if not client_id or not client_secret:
        raise AuraConfigurationError(f"{ENV_CLIENT_ID} and {ENV_CLIENT_SECRET} must both be set")
    return client_id, client_secret


class AuraClient:
    """Client for the Neo4j Aura API v1.

    Example::

        with AuraClient(client_id="...", client_secret="...") as client:
            for instance in client.instances.list():
                print(instance.id, instance.name)

    Services, mirroring the Go SDK: ``tenants``, ``instances``, ``snapshots``, ``cmek`` and
    ``graph_analytics``, plus ``prometheus`` for metrics endpoints.

    Every option is keyword-only. Invalid options raise :class:`AuraConfigurationError`.

    Args:
        client_id: Aura API client ID.
        client_secret: Aura API client secret.
        base_url: API base URL. It must use HTTPS unless ``allow_insecure_base_url`` is set.
        allow_insecure_base_url: Allow an ``http://`` base URL, and Prometheus URLs outside
            ``https://*.neo4j.io``. Only for local test servers, because credentials would be sent
            in cleartext.
        timeout: Seconds allowed for each API call, covering the token fetch, retries and backoff.
        max_retries: How many times to retry after a network failure. Responses with an HTTP
            status are never retried.
        max_response_size: Largest response body accepted, in bytes.
        user_agent: Overrides the ``User-Agent`` header.
        default_headers: Extra headers sent with every API request. ``Authorization``,
            ``Content-Type`` and ``User-Agent`` are ignored.
        logger: Logger for SDK diagnostics. Defaults to the ``aura_python_sdk`` logger.
        transport: Custom :class:`HttpTransport`. The client does not close a transport it
            did not create.
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        base_url: str = DEFAULT_BASE_URL,
        allow_insecure_base_url: bool = False,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_response_size: int = DEFAULT_MAX_RESPONSE_SIZE,
        user_agent: str = DEFAULT_USER_AGENT,
        default_headers: Mapping[str, str] | None = None,
        logger: logging.Logger | None = None,
        transport: HttpTransport | None = None,
    ) -> None:
        self._config: ClientConfig = build_config(
            client_id=client_id,
            client_secret=client_secret,
            base_url=base_url,
            allow_insecure_base_url=allow_insecure_base_url,
            timeout=timeout,
            max_retries=max_retries,
            max_response_size=max_response_size,
            user_agent=user_agent,
            default_headers=default_headers,
        )
        if transport is not None and (
            not isinstance(transport, HttpTransport) or inspect.iscoroutinefunction(transport.send)
        ):
            raise AuraConfigurationError(
                "transport must implement send() and close(); use AsyncAuraClient for an "
                "async transport"
            )
        self._logger = _resolve_logger(logger)
        self._owns_transport = transport is None
        self._transport: HttpTransport = transport or HttpxTransport()
        self._closed = False

        http = HttpService(
            self._transport,
            max_retries=self._config.max_retries,
            max_response_size=self._config.max_response_size,
            logger=self._logger.getChild("http"),
        )
        auth = TokenManager(
            client_id=self._config.client_id,
            client_secret=self._config.client_secret,
            token_url=f"{self._config.base_url}/oauth/token",
            user_agent=self._config.user_agent,
            http=http,
            logger=self._logger.getChild("auth"),
        )
        self._api = RequestService(
            http=http,
            auth=auth,
            base_url=self._config.base_url,
            api_version=API_VERSION,
            user_agent=self._config.user_agent,
            default_headers=self._config.default_headers,
            timeout=self._config.timeout,
            logger=self._logger.getChild("api"),
            is_closed=lambda: self._closed,
        )

        self.tenants = TenantService(self._api, self._logger.getChild("tenants"))
        self.instances = InstanceService(self._api, self._logger.getChild("instances"))
        self.snapshots = SnapshotService(self._api, self._logger.getChild("snapshots"))
        self.cmek = CMEKService(self._api, self._logger.getChild("cmek"))
        self.graph_analytics = GDSSessionService(
            self._api, self._logger.getChild("graph_analytics")
        )
        self.prometheus = PrometheusService(
            self._api,
            self._logger.getChild("prometheus"),
            allow_untrusted_urls=self._config.allow_insecure_base_url,
        )

        self._logger.debug(
            "Aura API client initialized",
            extra={"base_url": self._config.base_url, "api_version": API_VERSION},
        )

    @classmethod
    def from_env(cls, **options: object) -> Self:
        """Build a client with credentials from ``AURA_CLIENT_ID`` and ``AURA_CLIENT_SECRET``.

        Any other keyword option is passed through to :class:`AuraClient`.
        """
        client_id, client_secret = _env_credentials()
        return cls(client_id=client_id, client_secret=client_secret, **options)  # type: ignore[arg-type]

    @property
    def base_url(self) -> str:
        return self._config.base_url

    def close(self) -> None:
        """Release pooled connections. Safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        if self._owns_transport:
            self._transport.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"AuraClient(base_url={self._config.base_url!r})"


class AsyncAuraClient:
    """Async client for the Neo4j Aura API v1, for use with ``asyncio``.

    Takes the same options as :class:`AuraClient`, and its services have the same methods,
    which are awaited::

        async with AsyncAuraClient(client_id="...", client_secret="...") as client:
            instances = await client.instances.list()

    ``transport`` must be an :class:`AsyncHttpTransport`. Call :meth:`aclose`, or use
    ``async with``, to release connections.
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        base_url: str = DEFAULT_BASE_URL,
        allow_insecure_base_url: bool = False,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_response_size: int = DEFAULT_MAX_RESPONSE_SIZE,
        user_agent: str = DEFAULT_USER_AGENT,
        default_headers: Mapping[str, str] | None = None,
        logger: logging.Logger | None = None,
        transport: AsyncHttpTransport | None = None,
    ) -> None:
        self._config: ClientConfig = build_config(
            client_id=client_id,
            client_secret=client_secret,
            base_url=base_url,
            allow_insecure_base_url=allow_insecure_base_url,
            timeout=timeout,
            max_retries=max_retries,
            max_response_size=max_response_size,
            user_agent=user_agent,
            default_headers=default_headers,
        )
        if transport is not None and (
            not isinstance(transport, AsyncHttpTransport)
            or not inspect.iscoroutinefunction(transport.send)
        ):
            raise AuraConfigurationError(
                "transport must implement async send() and aclose(); use AuraClient for a "
                "sync transport"
            )
        self._logger = _resolve_logger(logger)
        self._owns_transport = transport is None
        self._transport: AsyncHttpTransport = transport or AsyncHttpxTransport()
        self._closed = False

        http = AsyncHttpService(
            self._transport,
            max_retries=self._config.max_retries,
            max_response_size=self._config.max_response_size,
            logger=self._logger.getChild("http"),
        )
        auth = AsyncTokenManager(
            client_id=self._config.client_id,
            client_secret=self._config.client_secret,
            token_url=f"{self._config.base_url}/oauth/token",
            user_agent=self._config.user_agent,
            http=http,
            logger=self._logger.getChild("auth"),
        )
        self._api = AsyncRequestService(
            http=http,
            auth=auth,
            base_url=self._config.base_url,
            api_version=API_VERSION,
            user_agent=self._config.user_agent,
            default_headers=self._config.default_headers,
            timeout=self._config.timeout,
            logger=self._logger.getChild("api"),
            is_closed=lambda: self._closed,
        )

        self.tenants = AsyncTenantService(self._api, self._logger.getChild("tenants"))
        self.instances = AsyncInstanceService(self._api, self._logger.getChild("instances"))
        self.snapshots = AsyncSnapshotService(self._api, self._logger.getChild("snapshots"))
        self.cmek = AsyncCMEKService(self._api, self._logger.getChild("cmek"))
        self.graph_analytics = AsyncGDSSessionService(
            self._api, self._logger.getChild("graph_analytics")
        )
        self.prometheus = AsyncPrometheusService(
            self._api,
            self._logger.getChild("prometheus"),
            allow_untrusted_urls=self._config.allow_insecure_base_url,
        )

    @classmethod
    def from_env(cls, **options: object) -> Self:
        """Build a client with credentials from ``AURA_CLIENT_ID`` and ``AURA_CLIENT_SECRET``."""
        client_id, client_secret = _env_credentials()
        return cls(client_id=client_id, client_secret=client_secret, **options)  # type: ignore[arg-type]

    @property
    def base_url(self) -> str:
        return self._config.base_url

    async def aclose(self) -> None:
        """Release pooled connections. Safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        if self._owns_transport:
            await self._transport.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    def __repr__(self) -> str:
        return f"AsyncAuraClient(base_url={self._config.base_url!r})"
