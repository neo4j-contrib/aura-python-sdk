"""``client.instances`` (Go: InstanceService)."""

from __future__ import annotations

import builtins
from collections.abc import Sequence

from aura_python_sdk import _validation as validate
from aura_python_sdk._errors import AuraValidationError
from aura_python_sdk._internal._call import Call, many, one
from aura_python_sdk._internal._request import build_path
from aura_python_sdk._internal._serde import to_json
from aura_python_sdk.models._common import InstanceType
from aura_python_sdk.models.instances import (
    CDCEnrichmentMode,
    CreatedInstance,
    Instance,
    InstanceConfig,
    InstanceSizeEstimate,
    InstanceSummary,
)
from aura_python_sdk.services._base import TENANT_ID_PARAM, AsyncService, Service

# --- Operations (validation, request and parsing; no I/O) ---


def _list(tenant_id: str | None) -> Call[list[InstanceSummary]]:
    if tenant_id is not None:
        tenant_id = validate.tenant_id(tenant_id)
    return Call(
        method="GET",
        path="instances",
        params={TENANT_ID_PARAM: tenant_id},
        parse=many(InstanceSummary),
        describe="listing instances",
        context={"tenant_id": tenant_id},
    )


def _get(instance_id: str) -> Call[Instance]:
    instance_id = validate.instance_id(instance_id)
    return Call(
        method="GET",
        path=build_path("instances", instance_id),
        parse=one(Instance),
        describe="getting instance",
        context={"instance_id": instance_id},
    )


def _create(
    config: InstanceConfig,
    source_instance_id: str | None = None,
    source_snapshot_id: str | None = None,
) -> Call[CreatedInstance]:
    if source_instance_id is not None:
        source_instance_id = validate.instance_id(source_instance_id, "source instance ID")
    if source_snapshot_id is not None:
        source_snapshot_id = validate.snapshot_id(source_snapshot_id, "source snapshot ID")
    body = _create_body(config)
    if source_instance_id is not None:
        body["source_instance_id"] = source_instance_id
    if source_snapshot_id is not None:
        body["source_snapshot_id"] = source_snapshot_id
    return Call(
        method="POST",
        path="instances",
        json_body=body,
        parse=one(CreatedInstance),
        describe="creating instance",
        done="instance creation started",
        context={"instance_name": config.name, "tenant_id": config.tenant_id},
    )


def _update(
    instance_id: str,
    *,
    name: str | None,
    memory: str | None,
    storage: str | None,
    vector_optimized: bool | None,
    graph_analytics_plugin: bool | None,
    cdc_enrichment_mode: CDCEnrichmentMode | str | None,
    secondaries_count: int | None,
) -> Call[Instance]:
    instance_id = validate.instance_id(instance_id)
    changes: dict[str, object] = {}
    if name is not None:
        changes["name"] = validate.instance_name(name)
    if memory is not None:
        changes["memory"] = validate.require_non_empty("memory", memory)
    if storage is not None:
        changes["storage"] = validate.require_non_empty("storage", storage)
    if vector_optimized is not None:
        changes["vector_optimized"] = validate.boolean("vector optimized", vector_optimized)
    if graph_analytics_plugin is not None:
        changes["graph_analytics_plugin"] = validate.boolean(
            "graph analytics plugin", graph_analytics_plugin
        )
    if cdc_enrichment_mode is not None:
        changes["cdc_enrichment_mode"] = validate.require_non_empty(
            "CDC enrichment mode", cdc_enrichment_mode
        )
    if secondaries_count is not None:
        changes["secondaries_count"] = validate.non_negative_int(
            "secondaries count", secondaries_count
        )
    if not changes:
        raise AuraValidationError("update requires at least one field to change")
    return Call(
        method="PATCH",
        path=build_path("instances", instance_id),
        json_body=to_json(changes),
        parse=one(Instance),
        describe="updating instance",
        done="instance update started",
        context={"instance_id": instance_id, "fields": sorted(changes)},
    )


def _estimate_size(
    node_count: int,
    relationship_count: int,
    instance_type: InstanceType | str | None,
    algorithm_categories: Sequence[str] | None,
) -> Call[InstanceSizeEstimate]:
    body: dict[str, object] = {
        "node_count": validate.non_negative_int("node count", node_count),
        "relationship_count": validate.non_negative_int("relationship count", relationship_count),
    }
    if instance_type is not None:
        body["instance_type"] = validate.require_non_empty("instance type", instance_type)
    if algorithm_categories is not None:
        body["algorithm_categories"] = validate.string_list(
            "algorithm categories", algorithm_categories
        )
    return Call(
        method="POST",
        path="instances/sizing",
        json_body=to_json(body),
        parse=one(InstanceSizeEstimate),
        describe="estimating instance size",
    )


def _upgrade(instance_id: str, memory: str | None, storage: str | None) -> Call[Instance]:
    instance_id = validate.instance_id(instance_id)
    if (memory is None) != (storage is None):
        raise AuraValidationError("upgrade requires both memory and storage, or neither")
    body: dict[str, object] = {}
    if memory is not None and storage is not None:
        body["memory"] = validate.require_non_empty("memory", memory)
        body["storage"] = validate.require_non_empty("storage", storage)
    return Call(
        method="POST",
        path=build_path("instances", instance_id, "upgrade"),
        json_body=body,
        parse=one(Instance),
        describe="upgrading instance",
        done="instance upgrade started",
        context={"instance_id": instance_id},
    )


def _delete(instance_id: str) -> Call[Instance]:
    instance_id = validate.instance_id(instance_id)
    return Call(
        method="DELETE",
        path=build_path("instances", instance_id),
        parse=one(Instance),
        describe="deleting instance",
        done="instance deletion started",
        context={"instance_id": instance_id},
    )


def _lifecycle(instance_id: str, action: str) -> Call[Instance]:
    instance_id = validate.instance_id(instance_id)
    return Call(
        method="POST",
        path=build_path("instances", instance_id, action),
        parse=one(Instance),
        describe=f"{action} instance",
        done=f"instance {action} started",
        context={"instance_id": instance_id},
    )


def _overwrite(
    instance_id: str,
    *,
    source_instance_id: str | None = None,
    source_snapshot_id: str | None = None,
) -> Call[Instance]:
    instance_id = validate.instance_id(instance_id)
    if source_instance_id is not None:
        body = {
            "source_instance_id": validate.instance_id(source_instance_id, "source instance ID")
        }
    else:
        body = {
            "source_snapshot_id": validate.snapshot_id(source_snapshot_id, "source snapshot ID")
        }
    return Call(
        method="POST",
        path=build_path("instances", instance_id, "overwrite"),
        json_body=body,
        parse=one(Instance),
        describe="overwriting instance",
        done="instance overwrite started",
        context={"instance_id": instance_id, **body},
    )


def _create_body(config: InstanceConfig) -> dict[str, object]:
    """Validate a create request as the Go SDK's validateCreateInstanceConfig does."""
    if not isinstance(config, InstanceConfig):
        raise AuraValidationError("config must be an InstanceConfig")
    validate.instance_name(config.name)
    validate.tenant_id(config.tenant_id)
    validate.require_non_empty("cloud provider", config.cloud_provider)
    validate.require_non_empty("region", config.region)
    validate.require_non_empty("instance type", config.type)
    validate.require_non_empty("version", config.version)
    validate.require_non_empty("memory", config.memory)
    if config.customer_managed_key_id is not None:
        validate.require_non_empty("customer managed key ID", config.customer_managed_key_id)
    body = to_json(config)
    if not isinstance(body, dict):  # pragma: no cover - to_json of a dataclass is a dict
        raise TypeError("expected a JSON object")
    return body


# --- Services ---


class InstanceService(Service):
    """AuraDB and AuraDS instances."""

    def list(self, tenant_id: str | None = None) -> builtins.list[InstanceSummary]:
        """Every instance the credentials can access, optionally only those in one tenant."""
        return self._run(_list(tenant_id))

    def get(self, instance_id: str) -> Instance:
        """Full details of one instance."""
        return self._run(_get(instance_id))

    def create(self, config: InstanceConfig) -> CreatedInstance:
        """Start creating an instance.

        Creation is asynchronous. Poll :meth:`get` until ``status`` is ``running``. The returned
        password is shown only once.
        """
        return self._run(_create(config))

    def create_from_instance(
        self, source_instance_id: str, config: InstanceConfig
    ) -> CreatedInstance:
        """Create an instance cloned from the current data of another instance."""
        return self._run(_create(config, source_instance_id=source_instance_id))

    def create_from_snapshot(
        self, source_instance_id: str, source_snapshot_id: str, config: InstanceConfig
    ) -> CreatedInstance:
        """Create an instance from a snapshot.

        The snapshot must belong to ``source_instance_id`` and be exportable.
        """
        return self._run(_create(config, source_instance_id, source_snapshot_id))

    def update(
        self,
        instance_id: str,
        *,
        name: str | None = None,
        memory: str | None = None,
        storage: str | None = None,
        vector_optimized: bool | None = None,
        graph_analytics_plugin: bool | None = None,
        cdc_enrichment_mode: CDCEnrichmentMode | str | None = None,
        secondaries_count: int | None = None,
    ) -> Instance:
        """Rename, resize or reconfigure an instance. Only the arguments given are changed.

        The update is asynchronous, and the instance stays available throughout.
        ``secondaries_count`` applies only to Virtual Dedicated Cloud, and
        ``cdc_enrichment_mode`` only to Virtual Dedicated Cloud and Business Critical.
        """
        return self._run(
            _update(
                instance_id,
                name=name,
                memory=memory,
                storage=storage,
                vector_optimized=vector_optimized,
                graph_analytics_plugin=graph_analytics_plugin,
                cdc_enrichment_mode=cdc_enrichment_mode,
                secondaries_count=secondaries_count,
            )
        )

    def estimate_size(
        self,
        *,
        node_count: int,
        relationship_count: int,
        instance_type: InstanceType | str | None = None,
        algorithm_categories: Sequence[str] | None = None,
    ) -> InstanceSizeEstimate:
        """Estimate the instance size needed for a graph.

        Supported for ``enterprise-ds`` and ``professional-ds``. Pass the recommended size as
        ``memory`` when creating the instance.
        """
        return self._run(
            _estimate_size(node_count, relationship_count, instance_type, algorithm_categories)
        )

    def upgrade(
        self, instance_id: str, *, memory: str | None = None, storage: str | None = None
    ) -> Instance:
        """Upgrade an AuraDB Professional instance to Business Critical.

        Pass both ``memory`` and ``storage`` to resize as part of the upgrade, or neither to keep
        the current size. Not available for Marketplace projects or trial instances.
        """
        return self._run(_upgrade(instance_id, memory, storage))

    def delete(self, instance_id: str) -> Instance:
        """Start deleting an instance. This cannot be undone."""
        return self._run(_delete(instance_id))

    def pause(self, instance_id: str) -> Instance:
        """Pause a running instance."""
        return self._run(_lifecycle(instance_id, "pause"))

    def resume(self, instance_id: str) -> Instance:
        """Resume a paused instance."""
        return self._run(_lifecycle(instance_id, "resume"))

    def overwrite_from_instance(self, instance_id: str, source_instance_id: str) -> Instance:
        """Replace an instance's data with the current data of another instance."""
        return self._run(_overwrite(instance_id, source_instance_id=source_instance_id))

    def overwrite_from_snapshot(self, instance_id: str, source_snapshot_id: str) -> Instance:
        """Replace an instance's data with a snapshot."""
        return self._run(_overwrite(instance_id, source_snapshot_id=source_snapshot_id))


class AsyncInstanceService(AsyncService):
    """Async version of :class:`InstanceService`, with the same arguments and behaviour."""

    async def list(self, tenant_id: str | None = None) -> builtins.list[InstanceSummary]:
        """See :meth:`InstanceService.list`."""
        return await self._run(_list(tenant_id))

    async def get(self, instance_id: str) -> Instance:
        """See :meth:`InstanceService.get`."""
        return await self._run(_get(instance_id))

    async def create(self, config: InstanceConfig) -> CreatedInstance:
        """See :meth:`InstanceService.create`."""
        return await self._run(_create(config))

    async def create_from_instance(
        self, source_instance_id: str, config: InstanceConfig
    ) -> CreatedInstance:
        """See :meth:`InstanceService.create_from_instance`."""
        return await self._run(_create(config, source_instance_id=source_instance_id))

    async def create_from_snapshot(
        self, source_instance_id: str, source_snapshot_id: str, config: InstanceConfig
    ) -> CreatedInstance:
        """See :meth:`InstanceService.create_from_snapshot`."""
        return await self._run(_create(config, source_instance_id, source_snapshot_id))

    async def update(
        self,
        instance_id: str,
        *,
        name: str | None = None,
        memory: str | None = None,
        storage: str | None = None,
        vector_optimized: bool | None = None,
        graph_analytics_plugin: bool | None = None,
        cdc_enrichment_mode: CDCEnrichmentMode | str | None = None,
        secondaries_count: int | None = None,
    ) -> Instance:
        """See :meth:`InstanceService.update`."""
        return await self._run(
            _update(
                instance_id,
                name=name,
                memory=memory,
                storage=storage,
                vector_optimized=vector_optimized,
                graph_analytics_plugin=graph_analytics_plugin,
                cdc_enrichment_mode=cdc_enrichment_mode,
                secondaries_count=secondaries_count,
            )
        )

    async def estimate_size(
        self,
        *,
        node_count: int,
        relationship_count: int,
        instance_type: InstanceType | str | None = None,
        algorithm_categories: Sequence[str] | None = None,
    ) -> InstanceSizeEstimate:
        """See :meth:`InstanceService.estimate_size`."""
        return await self._run(
            _estimate_size(node_count, relationship_count, instance_type, algorithm_categories)
        )

    async def upgrade(
        self, instance_id: str, *, memory: str | None = None, storage: str | None = None
    ) -> Instance:
        """See :meth:`InstanceService.upgrade`."""
        return await self._run(_upgrade(instance_id, memory, storage))

    async def delete(self, instance_id: str) -> Instance:
        """See :meth:`InstanceService.delete`."""
        return await self._run(_delete(instance_id))

    async def pause(self, instance_id: str) -> Instance:
        """See :meth:`InstanceService.pause`."""
        return await self._run(_lifecycle(instance_id, "pause"))

    async def resume(self, instance_id: str) -> Instance:
        """See :meth:`InstanceService.resume`."""
        return await self._run(_lifecycle(instance_id, "resume"))

    async def overwrite_from_instance(self, instance_id: str, source_instance_id: str) -> Instance:
        """See :meth:`InstanceService.overwrite_from_instance`."""
        return await self._run(_overwrite(instance_id, source_instance_id=source_instance_id))

    async def overwrite_from_snapshot(self, instance_id: str, source_snapshot_id: str) -> Instance:
        """See :meth:`InstanceService.overwrite_from_snapshot`."""
        return await self._run(_overwrite(instance_id, source_snapshot_id=source_snapshot_id))
