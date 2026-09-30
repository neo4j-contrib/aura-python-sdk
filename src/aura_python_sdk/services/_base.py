from __future__ import annotations

import logging
from typing import TypeVar

from aura_python_sdk._errors import AuraError
from aura_python_sdk._internal._call import Call
from aura_python_sdk._internal._request import AsyncRequestService, RequestService

T = TypeVar("T")

# List-filter query parameter names, as the v1 spec defines them. (The Go SDK sends tenant_id.)
TENANT_ID_PARAM = "tenantId"
INSTANCE_ID_PARAM = "instanceId"
ORGANIZATION_ID_PARAM = "organizationId"


def _without_internal_frames(exc: AuraError) -> AuraError:
    """Drop the SDK's internal frames from an SDK error's traceback.

    The error message already says what went wrong, so the traceback starts at the service
    method the caller used. Unexpected exceptions (bugs) are not caught, and keep their full
    traceback.
    """
    return exc.with_traceback(None)


class Service:
    """Base for the sync services on :class:`AuraClient`: runs each operation's ``Call``."""

    def __init__(self, api: RequestService, logger: logging.Logger) -> None:
        self._api = api
        self._logger = logger

    def _run(self, call: Call[T]) -> T:
        __tracebackhide__ = True  # pytest: leave this frame out of failure reports
        self._logger.debug(call.describe, extra=dict(call.context))
        try:
            response = self._api.request(
                call.method, call.path, params=call.params, json_body=call.json_body
            )
            result = call.parse(response)
        except AuraError as exc:
            # Re-raising the same object keeps its __cause__ (e.g. the network error).
            raise _without_internal_frames(exc)  # noqa: B904
        if call.done:
            self._logger.info(call.done, extra=dict(call.context))
        return result


class AsyncService:
    """Base for the async services on :class:`AsyncAuraClient`: awaits each operation's ``Call``."""

    def __init__(self, api: AsyncRequestService, logger: logging.Logger) -> None:
        self._api = api
        self._logger = logger

    async def _run(self, call: Call[T]) -> T:
        __tracebackhide__ = True  # pytest: leave this frame out of failure reports
        self._logger.debug(call.describe, extra=dict(call.context))
        try:
            response = await self._api.request(
                call.method, call.path, params=call.params, json_body=call.json_body
            )
            result = call.parse(response)
        except AuraError as exc:
            # Re-raising the same object keeps its __cause__ (e.g. the network error).
            raise _without_internal_frames(exc)  # noqa: B904
        if call.done:
            self._logger.info(call.done, extra=dict(call.context))
        return result
