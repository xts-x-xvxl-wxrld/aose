import sys
import importlib
import importlib.util
import pytest


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows boundary rule: worker tests must run in Linux container",
)
def test_worker_entrypoint_module_exists():
    assert importlib.import_module("aose_worker.run_worker") is not None
