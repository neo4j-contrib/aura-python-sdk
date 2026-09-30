"""``client.graph_analytics`` (Go: GDSSessionService)."""

from __future__ import annotations

import builtins
from collections.abc import Sequence

from aura_python_sdk import _validation as validate
from aura_python_sdk._errors import AuraValidationError
from aura_python_sdk._internal._call import Call, many, one
from aura_python_sdk._internal._request import build_path
from aura_python_sdk._internal._serde import to_json
from aura_python_sdk._internal._wait import DEFAULT_WAIT_INTERVAL, DEFAULT_WAIT_TIMEOUT, Target
from aura_python_sdk.models.graph_analytics import (
    DeletedGDSSession,
    GDSSession,
    GDSSessionConfig,
    GDSSessionSizeEstimate,
    GDSSessionStatus,
)
from aura_python_sdk.services._base import (
    INSTANCE_ID_PARAM,
    ORGANIZATION_ID_PARAM,
    TENANT_ID_PARAM,
    AsyncService,
    Service,
)

_SESSIONS = "graph-analytics/sessions"

# --- Operations (validation, request and parsing; no I/O) ---


def _list(
    tenant_id: str | None, instance_id: str | None, organization_id: str | None
) -> Call[list[GDSSession]]:
    params = {
        TENANT_ID_PARAM: None if tenant_id is None else validate.tenant_id(tenant_id),
        INSTANCE_ID_PARAM: None if instance_id is None else validate.instance_id(instance_id),
        ORGANIZATION_ID_PARAM: None
        if organization_id is None
        else validate.require_non_empty("organization ID", organization_id),
    }
    return Call(
        method="GET",
        path=_SESSIONS,
        params=params,
        parse=many(GDSSession),
        describe="listing GDS sessions",
    )


def _estimate_size(
    node_count: int,
    relationship_count: int,
    node_property_count: int | None,
    node_label_count: int | None,
    relationship_property_count: int | None,
    algorithm_categories: Sequence[str] | None,
) -> Call[GDSSessionSizeEstimate]:
    body: dict[str, object] = {
        "node_count": validate.non_negative_int("node count", node_count),
        "relationship_count": validate.non_negative_int("relationship count", relationship_count),
    }
    optional_counts = {
        "node_property_count": node_property_count,
        "node_label_count": node_label_count,
        "relationship_property_count": relationship_property_count,
    }
    for key, value in optional_counts.items():
        if value is not None:
            body[key] = validate.non_negative_int(key.replace("_", " "), value)
    if algorithm_categories is not None:
        body["algorithm_categories"] = validate.string_list(
            "algorithm categories", algorithm_categories
        )
    return Call(
        method="POST",
        path=f"{_SESSIONS}/sizing",
        json_body=body,
        parse=one(GDSSessionSizeEstimate),
        describe="estimating GDS session size",
    )


def _create(config: GDSSessionConfig) -> Call[GDSSession]:
    if not isinstance(config, GDSSessionConfig):
        raise AuraValidationError("config must be a GDSSessionConfig")
    validate.require_non_empty("session name", config.name)
    validate.require_non_empty("memory", config.memory)
    if config.tenant_id is not None:
        validate.tenant_id(config.tenant_id)
    if config.instance_id is not None:
        validate.instance_id(config.instance_id)
    return Call(
        method="POST",
        path=_SESSIONS,
        json_body=to_json(config),
        parse=one(GDSSession),
        describe="creating GDS session",
        done="GDS session created",
        context={"session_name": config.name},
    )


def _get(session_id: str) -> Call[GDSSession]:
    session_id = validate.session_id(session_id)
    return Call(
        method="GET",
        path=build_path("graph-analytics", "sessions", session_id),
        parse=one(GDSSession),
        describe="getting GDS session",
        context={"session_id": session_id},
    )


def _delete(session_id: str) -> Call[DeletedGDSSession]:
    session_id = validate.session_id(session_id)
    return Call(
        method="DELETE",
        path=build_path("graph-analytics", "sessions", session_id),
        parse=one(DeletedGDSSession),
        describe="deleting GDS session",
        done="GDS session deleted",
        context={"session_id": session_id},
    )


def _ready_target(session_id: str) -> Target[GDSSession]:
    session_id = validate.session_id(session_id)
    return Target(
        describe=f"GDS session {session_id} to be ready",
        status=lambda session: session.status,
        done=GDSSessionStatus.READY,
        failed={GDSSessionStatus.FAILED, GDSSessionStatus.EXPIRED},
    )


# --- Services ---


class GDSSessionService(Service):
    """Graph Analytics (GDS) sessions.

    Each method lists the errors specific to it. The errors any call can raise are listed on
    :class:`~aura_python_sdk.AuraClient`.
    """

    def list(
        self,
        *,
        tenant_id: str | None = None,
        instance_id: str | None = None,
        organization_id: str | None = None,
    ) -> builtins.list[GDSSession]:
        """Every session the credentials can access, optionally filtered.

        Raises:
            AuraValidationError: A filter is invalid; nothing was sent.
        """
        return self._run(_list(tenant_id, instance_id, organization_id))

    def estimate_size(
        self,
        *,
        node_count: int,
        relationship_count: int,
        node_property_count: int | None = None,
        node_label_count: int | None = None,
        relationship_property_count: int | None = None,
        algorithm_categories: Sequence[str] | None = None,
    ) -> GDSSessionSizeEstimate:
        """Estimate the session size needed for a graph (Go: ``Estimate``).

        Raises:
            AuraValidationError: An argument is invalid; nothing was sent.
        """
        return self._run(
            _estimate_size(
                node_count,
                relationship_count,
                node_property_count,
                node_label_count,
                relationship_property_count,
                algorithm_categories,
            )
        )

    def create(self, config: GDSSessionConfig) -> GDSSession:
        """Create a session, or return the matching existing one.

        Attach it to an instance with ``instance_id`` and ``database_uuid``, or make a standalone
        session with ``cloud_provider`` and ``region``.

        Raises:
            AuraValidationError: A field of ``config`` is invalid; nothing was sent.
        """
        return self._run(_create(config))

    def get(self, session_id: str) -> GDSSession:
        """Details of one session.

        Raises:
            AuraValidationError: ``session_id`` is invalid; nothing was sent.
            NotFoundError: The session doesn't exist.
        """
        return self._run(_get(session_id))

    def delete(self, session_id: str) -> DeletedGDSSession:
        """Delete a session.

        Raises:
            AuraValidationError: ``session_id`` is invalid; nothing was sent.
            NotFoundError: The session doesn't exist.
        """
        return self._run(_delete(session_id))

    def wait_until_ready(
        self,
        session_id: str,
        *,
        timeout: float = DEFAULT_WAIT_TIMEOUT,
        interval: float = DEFAULT_WAIT_INTERVAL,
    ) -> GDSSession:
        """Poll :meth:`get` until the session is ``Ready``, and return it.

        ``timeout`` and ``interval`` are in seconds (15 minutes and 10 seconds by default).

        Raises:
            OperationFailedError: The session ``Failed`` or ``Expired``.
            WaitTimeoutError: ``timeout`` passed first. The session may still become ready.
            NotFoundError: It still wasn't found after a minute.
        """
        target = _ready_target(session_id)
        return self._wait(lambda: self.get(session_id), target, timeout, interval)


class AsyncGDSSessionService(AsyncService):
    """Async version of :class:`GDSSessionService`, with the same arguments and behaviour."""

    async def list(
        self,
        *,
        tenant_id: str | None = None,
        instance_id: str | None = None,
        organization_id: str | None = None,
    ) -> builtins.list[GDSSession]:
        """See :meth:`GDSSessionService.list`."""
        return await self._run(_list(tenant_id, instance_id, organization_id))

    async def estimate_size(
        self,
        *,
        node_count: int,
        relationship_count: int,
        node_property_count: int | None = None,
        node_label_count: int | None = None,
        relationship_property_count: int | None = None,
        algorithm_categories: Sequence[str] | None = None,
    ) -> GDSSessionSizeEstimate:
        """See :meth:`GDSSessionService.estimate_size`."""
        return await self._run(
            _estimate_size(
                node_count,
                relationship_count,
                node_property_count,
                node_label_count,
                relationship_property_count,
                algorithm_categories,
            )
        )

    async def create(self, config: GDSSessionConfig) -> GDSSession:
        """See :meth:`GDSSessionService.create`."""
        return await self._run(_create(config))

    async def get(self, session_id: str) -> GDSSession:
        """See :meth:`GDSSessionService.get`."""
        return await self._run(_get(session_id))

    async def delete(self, session_id: str) -> DeletedGDSSession:
        """See :meth:`GDSSessionService.delete`."""
        return await self._run(_delete(session_id))

    async def wait_until_ready(
        self,
        session_id: str,
        *,
        timeout: float = DEFAULT_WAIT_TIMEOUT,
        interval: float = DEFAULT_WAIT_INTERVAL,
    ) -> GDSSession:
        """See :meth:`GDSSessionService.wait_until_ready`."""
        target = _ready_target(session_id)
        return await self._wait(lambda: self.get(session_id), target, timeout, interval)
