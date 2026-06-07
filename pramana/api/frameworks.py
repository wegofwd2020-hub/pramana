"""``/frameworks`` — the definitions-library feed for the commissioning UI.

Read-only views over :mod:`pramana.services.definitions_library`: the framework
picker and a framework's citable clause anchors (US-PLATFORM-0003). The clauses
listed here are exactly the anchors a Package Request's ``source_definitions``
may cite — a request referencing anything else is rejected at commission.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from pramana.api.dependencies import get_definitions_root, get_principal
from pramana.api.schemas import FrameworkClauseOut, FrameworkOut
from pramana.services import definitions_library as dl

router = APIRouter(
    prefix="/frameworks",
    tags=["Frameworks"],
    dependencies=[Depends(get_principal)],
)

Root = Annotated[Path, Depends(get_definitions_root)]


@router.get("", response_model=list[FrameworkOut], summary="List frameworks in the library")
async def list_frameworks(root: Root) -> list[FrameworkOut]:
    return [FrameworkOut.of(fw) for fw in dl.list_frameworks(root)]


@router.get(
    "/{framework}/clauses",
    response_model=list[FrameworkClauseOut],
    summary="List a framework's clause anchors",
)
async def list_clauses(framework: str, root: Root) -> list[FrameworkClauseOut]:
    return [FrameworkClauseOut.of(c) for c in dl.list_clauses(root, framework)]
