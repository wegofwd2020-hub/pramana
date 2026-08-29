"""The Makefile's entrypoints actually resolve.

``make run`` pointed at ``pramana.api.main:app`` — a module that has never
existed — so the documented way to start the application failed, and nothing
noticed. The test suite builds ``create_app()`` in process; it never resolves the
target a developer or a container would use.

This is cheap and it closes that specific gap: a target naming an import path is
checked against the actual code.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

MAKEFILE = Path(__file__).resolve().parents[1] / "Makefile"

#: ``uvicorn [--factory] module:attr`` — captures the module path and attribute.
_UVICORN = re.compile(r"uvicorn\s+(?:--factory\s+)?([\w.]+):(\w+)")


def _makefile() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def _uvicorn_targets() -> list[tuple[str, str]]:
    return _UVICORN.findall(_makefile())


def test_the_makefile_declares_a_uvicorn_entrypoint() -> None:
    """Guard the guard: a silent rename would make the checks below vacuous."""
    assert _uvicorn_targets(), "no uvicorn target found in the Makefile"


@pytest.mark.parametrize(("module_path", "attribute"), _uvicorn_targets())
def test_uvicorn_target_resolves(module_path: str, attribute: str) -> None:
    """Every ``module:attr`` a Makefile hands uvicorn must actually exist."""
    module = importlib.import_module(module_path)
    assert hasattr(module, attribute), (
        f"Makefile points uvicorn at {module_path}:{attribute}, "
        f"but {attribute!r} is not defined there"
    )


@pytest.mark.parametrize(("module_path", "attribute"), _uvicorn_targets())
def test_uvicorn_factory_target_is_callable(module_path: str, attribute: str) -> None:
    """``--factory`` means uvicorn will call it; a plain object would fail at boot."""
    if "--factory" not in _makefile():
        pytest.skip("target is not declared as a factory")
    target = getattr(importlib.import_module(module_path), attribute)
    assert callable(target)


def test_no_target_references_a_celery_app_that_does_not_exist() -> None:
    """``make worker`` ran ``celery -A pramana.tasks`` with no Celery app defined.

    A target that always fails is worse than no target: it implies a capability
    the repo does not have. If a worker target returns, this test should be
    replaced with one that resolves the app.
    """
    if "celery -A" not in _makefile():
        return
    module_path = re.search(r"celery -A ([\w.]+)", _makefile())
    assert module_path is not None
    module = importlib.import_module(module_path.group(1))
    assert any(type(v).__name__ == "Celery" for v in vars(module).values()), (
        f"Makefile runs celery against {module_path.group(1)}, which defines no Celery application"
    )
