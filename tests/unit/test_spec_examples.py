"""Parse every 2xx response example in the v1 OpenAPI spec with its model.

If the spec adds an operation or a success response with a JSON body, the coverage test fails
until it is mapped to a model below.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from aura_python_sdk import models
from aura_python_sdk._internal._serde import parse_data, parse_data_list

SPEC_PATH = Path(__file__).resolve().parents[2] / "aura_api_spec_v1 .yaml"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


class _SpecLoader(yaml.SafeLoader):
    """SafeLoader that leaves timestamps as strings, as they would arrive in JSON."""


_SpecLoader.yaml_implicit_resolvers = {
    key: [(tag, regex) for tag, regex in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}

# (operationId, status) -> (model, is_list)
RESPONSE_MODELS: dict[tuple[str, str], tuple[type[Any], bool]] = {
    ("get-instances", "200"): (models.InstanceSummary, True),
    ("post-instances", "202"): (models.CreatedInstance, False),
    ("post-instances-sizing", "200"): (models.InstanceSizeEstimate, False),
    ("get-instance-id", "200"): (models.Instance, False),
    ("delete-instance-id", "202"): (models.Instance, False),
    ("patch-instance-id", "200"): (models.Instance, False),
    ("patch-instance-id", "202"): (models.Instance, False),
    ("post-overwrite-instance", "202"): (models.Instance, False),
    ("post-pause-instance", "202"): (models.Instance, False),
    ("post-resume-instance", "202"): (models.Instance, False),
    ("get-snapshot-snapshotid", "200"): (models.Snapshot, False),
    ("post-restore-snapshot", "202"): (models.Instance, False),
    ("get-snapshots", "200"): (models.Snapshot, True),
    ("post-snapshots", "202"): (models.CreatedSnapshot, False),
    ("post-upgrade-instance", "200"): (models.Instance, False),
    ("get-projects", "200"): (models.TenantSummary, True),
    ("get-project-id", "200"): (models.Tenant, False),
    ("get-customer-managed-keys", "200"): (models.CustomerManagedKeySummary, True),
    ("post-customer-managed-keys", "202"): (models.CustomerManagedKey, False),
    ("get-customer-managed-key-id", "200"): (models.CustomerManagedKey, False),
    ("get-project-metrics-integration-details", "200"): (models.MetricsIntegration, False),
    ("get-sessions", "200"): (models.GDSSession, True),
    ("post-session", "200"): (models.GDSSession, False),
    ("post-session", "202"): (models.GDSSession, False),
    ("post-sessions-sizing", "200"): (models.GDSSessionSizeEstimate, False),
    ("get-session", "200"): (models.GDSSession, False),
    ("delete-session", "202"): (models.DeletedGDSSession, False),
}


def _load_spec() -> dict[str, Any]:
    with SPEC_PATH.open(encoding="utf-8") as handle:
        spec: dict[str, Any] = yaml.load(handle, Loader=_SpecLoader)  # noqa: S506 - SafeLoader subclass
    return spec


def _success_responses() -> list[tuple[str, str, dict[str, Any]]]:
    """(operationId, status, application/json content) for every 2xx response with a body."""
    found = []
    for path_item in _load_spec()["paths"].values():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            for status, response in operation.get("responses", {}).items():
                content = (response or {}).get("content", {}).get("application/json")
                if str(status).startswith("2") and content:
                    found.append((operation["operationId"], str(status), content))
    return found


def _examples() -> list[Any]:
    cases = []
    for operation_id, status, content in _success_responses():
        values = []
        if "example" in content:
            values.append(("example", content["example"]))
        for name, example in (content.get("examples") or {}).items():
            values.append((name, example["value"]))
        for name, value in values:
            cases.append(
                pytest.param(operation_id, status, value, id=f"{operation_id}-{status}-{name}")
            )
    return cases


def test_every_success_response_has_a_model() -> None:
    documented = {(operation_id, status) for operation_id, status, _ in _success_responses()}
    assert documented - RESPONSE_MODELS.keys() == set()
    assert RESPONSE_MODELS.keys() - documented == set()


def test_spec_has_examples() -> None:
    assert len(_examples()) >= 25


@pytest.mark.parametrize(("operation_id", "status", "example"), _examples())
def test_spec_example_parses(operation_id: str, status: str, example: Any) -> None:
    model, is_list = RESPONSE_MODELS[(operation_id, status)]
    if is_list:
        parsed = parse_data_list(model, example)
        assert len(parsed) == len(example["data"])
        assert all(isinstance(item, model) for item in parsed)
    else:
        assert isinstance(parse_data(model, example), model)


# operationId -> "service.method" on AuraClient
OPERATION_METHODS = {
    "get-instances": "instances.list",
    "post-instances": "instances.create",
    "post-instances-sizing": "instances.estimate_size",
    "get-instance-id": "instances.get",
    "delete-instance-id": "instances.delete",
    "patch-instance-id": "instances.update",
    "post-overwrite-instance": "instances.overwrite_from_instance",
    "post-pause-instance": "instances.pause",
    "post-resume-instance": "instances.resume",
    "post-upgrade-instance": "instances.upgrade",
    "get-snapshots": "snapshots.list",
    "post-snapshots": "snapshots.create",
    "get-snapshot-snapshotid": "snapshots.get",
    "post-restore-snapshot": "snapshots.restore",
    "get-projects": "tenants.list",
    "get-project-id": "tenants.get",
    "get-project-metrics-integration-details": "tenants.get_metrics_integration",
    "get-customer-managed-keys": "cmek.list",
    "post-customer-managed-keys": "cmek.create",
    "get-customer-managed-key-id": "cmek.get",
    "delete-customer-managed-key-id": "cmek.delete",
    "get-sessions": "graph_analytics.list",
    "post-session": "graph_analytics.create",
    "post-sessions-sizing": "graph_analytics.estimate_size",
    "get-session": "graph_analytics.get",
    "delete-session": "graph_analytics.delete",
}


def test_every_spec_operation_has_a_client_method() -> None:
    from aura_python_sdk import AuraClient
    from tests.fakes import FakeTransport

    operation_ids = {
        operation["operationId"]
        for path_item in _load_spec()["paths"].values()
        for method, operation in path_item.items()
        if method in HTTP_METHODS
    }
    assert operation_ids == OPERATION_METHODS.keys()

    client = AuraClient(client_id="id", client_secret="secret", transport=FakeTransport())
    for dotted in OPERATION_METHODS.values():
        service_name, method_name = dotted.split(".")
        assert callable(getattr(getattr(client, service_name), method_name)), dotted
