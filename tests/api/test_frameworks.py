"""HTTP-layer tests for /frameworks (the definitions-library picker feed)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pramana.api.app import create_app
from pramana.api.dependencies import get_definitions_root, get_principal
from pramana.services.auth import Principal

_FCPA = "# Framework Reference: FCPA (Foreign Corrupt Practices Act)\n\n### Anti-bribery\nText.\n"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "framework_fcpa.md").write_text(_FCPA, encoding="utf-8")
    return tmp_path


def client(root: Path) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_definitions_root] = lambda: root
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=uuid.uuid4(), tenant_id=uuid.uuid4()
    )
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_list_frameworks(root: Path) -> None:
    c = next(client(root))
    resp = c.get("/frameworks")
    assert resp.status_code == 200
    body = resp.json()
    assert any(f["code"] == "fcpa" for f in body)


def test_list_clauses(root: Path) -> None:
    c = next(client(root))
    resp = c.get("/frameworks/fcpa/clauses")
    assert resp.status_code == 200
    clauses = {c_["clause"] for c_ in resp.json()}
    assert "anti-bribery" in clauses


def test_list_clauses_unknown_framework_404(root: Path) -> None:
    c = next(client(root))
    resp = c.get("/frameworks/hipaa/clauses")
    assert resp.status_code == 404
