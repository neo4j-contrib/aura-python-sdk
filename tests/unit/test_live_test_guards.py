"""Guards for the live integration tests, checked in CI where the live tests themselves don't run.

The write test creates a billed AuraDB Professional instance, so it must only run when
AURA_INTEGRATION_WRITE=1 and AURA_TENANT_ID are set.
"""

import os

import pytest

from tests.integration import test_live


def test_write_test_is_skipped_unless_writes_are_enabled() -> None:
    if os.environ.get("AURA_INTEGRATION_WRITE") == "1" and os.environ.get("AURA_TENANT_ID"):
        pytest.skip("writes are enabled in this environment")
    marks = getattr(test_live.test_create_pause_resume_delete, "pytestmark", [])
    skipifs = [mark for mark in marks if mark.name == "skipif"]
    assert skipifs, "the write test has lost its skipif decorator"
    assert all(mark.args[0] is True for mark in skipifs)


def test_only_tests_carry_the_write_guard() -> None:
    # The guard once ended up on a helper defined between the decorator and the test.
    for name, value in vars(test_live).items():
        if name.startswith("_") and callable(value):
            assert not getattr(value, "pytestmark", None), f"{name} has a pytest mark"
