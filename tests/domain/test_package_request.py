"""Tests for the Package Request domain (pure structural validation)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from pramana.domain.package_request import build_package_request
from pramana.exceptions import ValidationError


def _body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "framework": "fcpa",
        "title": "FCPA Anti-Bribery for At-Risk Roles",
        "scope": {"personas": ["employee"], "risk_tier": "high"},
        "source_definitions": [
            {"framework": "fcpa", "clause": "anti-bribery",
             "ref": "docs/frameworks/framework_fcpa.md#anti-bribery"}
        ],
        "learning_objectives": ["Recognise a foreign official"],
        "assessment": {"required": True, "pass_threshold_pct": 80, "min_questions": 8,
                       "style": "scenario-based"},
        "constraints": {"every_claim_cited": True, "length_minutes": 20},
        "deliverables": ["epub3", "pdf"],
        "visuals": ["animated_svg"],
        "satisfies_stories": ["US-FCPA-0001"],
    }
    body.update(overrides)
    return body


class TestHappyPath:
    def test_builds_full_request(self) -> None:
        req = build_package_request(_body())
        assert req.framework == "fcpa"
        assert req.title.startswith("FCPA")
        assert len(req.source_definitions) == 1
        assert req.source_definitions[0].clause == "anti-bribery"
        assert req.assessment.pass_threshold_pct == 80
        assert req.assessment.min_questions == 8
        assert req.deliverables == ("epub3", "pdf")
        assert req.visuals == ("animated_svg",)
        assert req.course_id is None

    def test_minimal_request_uses_defaults(self) -> None:
        req = build_package_request(
            {
                "framework": "sox",
                "title": "SOX 404",
                "source_definitions": [{"framework": "sox", "clause": "404"}],
                "assessment": {"pass_threshold_pct": 70},
            }
        )
        assert req.assessment.required is True
        assert req.assessment.style == "scenario-based"
        assert req.assessment.min_questions is None
        assert req.learning_objectives == ()
        assert req.deliverables == ()

    def test_course_id_parsed(self) -> None:
        cid = uuid.uuid4()
        req = build_package_request(_body(course_id=str(cid)))
        assert req.course_id == cid

    def test_as_payload_round_trips_author(self) -> None:
        req = build_package_request(_body())
        rid = uuid.uuid4()
        payload = req.as_payload(request_id=rid, requested_by="sme@x")
        assert payload["request_id"] == str(rid)
        assert payload["requested_by"] == "sme@x"
        assert payload["assessment"]["pass_threshold_pct"] == 80
        assert payload["source_definitions"][0]["clause"] == "anti-bribery"


class TestRejection:
    def test_not_an_object(self) -> None:
        with pytest.raises(ValidationError):
            build_package_request([1, 2])  # type: ignore[arg-type]

    def test_missing_framework(self) -> None:
        body = _body()
        del body["framework"]
        with pytest.raises(ValidationError):
            build_package_request(body)

    def test_blank_title(self) -> None:
        with pytest.raises(ValidationError):
            build_package_request(_body(title="  "))

    def test_empty_source_definitions(self) -> None:
        with pytest.raises(ValidationError):
            build_package_request(_body(source_definitions=[]))

    def test_clause_missing_clause_field(self) -> None:
        with pytest.raises(ValidationError):
            build_package_request(_body(source_definitions=[{"framework": "fcpa"}]))

    def test_blank_ref_rejected(self) -> None:
        with pytest.raises(ValidationError):
            build_package_request(
                _body(source_definitions=[{"framework": "f", "clause": "c", "ref": " "}])
            )

    def test_missing_assessment(self) -> None:
        body = _body()
        del body["assessment"]
        with pytest.raises(ValidationError):
            build_package_request(body)

    def test_threshold_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            build_package_request(_body(assessment={"pass_threshold_pct": 150}))

    def test_bad_style(self) -> None:
        with pytest.raises(ValidationError):
            build_package_request(_body(assessment={"pass_threshold_pct": 80, "style": "essay"}))

    def test_bad_risk_tier(self) -> None:
        with pytest.raises(ValidationError):
            build_package_request(_body(scope={"risk_tier": "extreme"}))

    def test_bad_deliverable(self) -> None:
        with pytest.raises(ValidationError):
            build_package_request(_body(deliverables=["docx"]))

    def test_bad_visual(self) -> None:
        with pytest.raises(ValidationError):
            build_package_request(_body(visuals=["gif"]))

    def test_bad_course_id(self) -> None:
        with pytest.raises(ValidationError):
            build_package_request(_body(course_id="not-a-uuid"))
