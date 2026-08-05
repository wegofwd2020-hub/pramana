"""End-to-end integration tests for the learner runtime (real Postgres).

Covers the take-the-quiz loop through the service layer + domain + DB:
assign -> (watch-gate) -> attempt -> grade -> pass/fail/retry/block -> certificate.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.assignment import Attempt, Certificate
from pramana.domain.enums import AssignmentStatus
from pramana.exceptions import (
    AuthorizationError,
    ConflictError,
    CooldownActiveError,
    InvalidStateTransitionError,
    ValidationError,
)
from pramana.services import assignments as svc
from pramana.services import certificates as cert_svc
from pramana.services import player as player_svc
from tests.integration.conftest import SeededCourse, seed_course

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


def _accept() -> svc.Attestation:
    return svc.Attestation(text_version="v1", accepted=True, ip="10.0.0.1", user_agent="pytest")


async def _assign(db: AsyncSession, seed: SeededCourse) -> uuid.UUID:
    a = await svc.create_assignment(
        db,
        tenant_id=seed.tenant_id,
        user_id=seed.user_id,
        course_id=seed.course_id,
        assigned_by_user_id=None,
        due_at=None,
        now=NOW,
    )
    await db.commit()
    return a.id


class TestHappyPath:
    async def test_assign_attempt_pass_issues_certificate(self, db: AsyncSession) -> None:
        seed = await seed_course(db, n_questions=2)
        assignment_id = await _assign(db, seed)

        attempt = await svc.start_attempt(
            db,
            assignment_id=assignment_id,
            tenant_id=seed.tenant_id,
            acting_user_id=seed.user_id,
            now=NOW,
        )
        await db.commit()
        assert attempt.attempt_number == 1

        # answer every question correctly
        answers = {qid: [correct] for qid, (correct, _wrong) in seed.questions.items()}
        result = await svc.submit_attempt(
            db,
            assignment_id=assignment_id,
            tenant_id=seed.tenant_id,
            acting_user_id=seed.user_id,
            answers=answers,
            attestation=_accept(),
            now=NOW,
        )
        await db.commit()

        assert result.snapshot.status is AssignmentStatus.PASSED
        assert result.grade.score_pct == 100.0
        assert result.retry_available is False
        assert result.certificate is not None
        assert result.certificate.course_version_id == seed.course_version_id
        assert len(result.certificate.verification_code) == 32

        # certificate persisted + verifiable
        found = await cert_svc.verify_by_code(
            db, verification_code=result.certificate.verification_code
        )
        assert found is not None and found.assignment_id == assignment_id


class TestRetryAndBlock:
    async def test_fail_then_carry_forward_pass(self, db: AsyncSession) -> None:
        seed = await seed_course(db, n_questions=2, pass_threshold_pct=80, max_attempts=2)
        assignment_id = await _assign(db, seed)
        qids = list(seed.questions)
        q_a, q_b = qids[0], qids[1]

        # Attempt 1: q_a right, q_b wrong -> 50% -> retry
        await svc.start_attempt(
            db,
            assignment_id=assignment_id,
            tenant_id=seed.tenant_id,
            acting_user_id=seed.user_id,
            now=NOW,
        )
        await db.commit()
        r1 = await svc.submit_attempt(
            db,
            assignment_id=assignment_id,
            tenant_id=seed.tenant_id,
            acting_user_id=seed.user_id,
            answers={q_a: [seed.questions[q_a][0]], q_b: [seed.questions[q_b][1]]},
            attestation=_accept(),
            now=NOW,
        )
        await db.commit()
        assert r1.snapshot.status is AssignmentStatus.ASSIGNED
        assert r1.retry_available is True
        assert r1.grade.score_pct == 50.0

        # Attempt 2: only re-answer q_b correctly; q_a carries forward -> 100%
        await svc.start_attempt(
            db,
            assignment_id=assignment_id,
            tenant_id=seed.tenant_id,
            acting_user_id=seed.user_id,
            now=NOW,
        )
        await db.commit()
        r2 = await svc.submit_attempt(
            db,
            assignment_id=assignment_id,
            tenant_id=seed.tenant_id,
            acting_user_id=seed.user_id,
            answers={q_b: [seed.questions[q_b][0]]},
            attestation=_accept(),
            now=NOW,
        )
        await db.commit()
        assert r2.snapshot.status is AssignmentStatus.PASSED
        assert r2.grade.score_pct == 100.0
        assert r2.attempt.attempt_number == 2

    async def test_fail_twice_blocks_no_certificate(self, db: AsyncSession) -> None:
        seed = await seed_course(db, n_questions=2, max_attempts=2)
        assignment_id = await _assign(db, seed)
        all_wrong = {qid: [wrong] for qid, (_c, wrong) in seed.questions.items()}

        for _ in range(2):
            await svc.start_attempt(
                db,
                assignment_id=assignment_id,
                tenant_id=seed.tenant_id,
                acting_user_id=seed.user_id,
                now=NOW,
            )
            await db.commit()
            result = await svc.submit_attempt(
                db,
                assignment_id=assignment_id,
                tenant_id=seed.tenant_id,
                acting_user_id=seed.user_id,
                answers=all_wrong,
                attestation=_accept(),
                now=NOW,
            )
            await db.commit()

        assert result.snapshot.status is AssignmentStatus.BLOCKED
        assert result.snapshot.cooldown_until is not None
        n_certs = (await db.execute(select(func.count()).select_from(Certificate))).scalar_one()
        assert n_certs == 0


class TestWatchGate:
    async def test_quiz_locked_until_watched(self, db: AsyncSession) -> None:
        seed = await seed_course(db, min_watch_pct=50)
        assignment_id = await _assign(db, seed)

        with pytest.raises(ValidationError, match="locked"):
            await svc.start_attempt(
                db,
                assignment_id=assignment_id,
                tenant_id=seed.tenant_id,
                acting_user_id=seed.user_id,
                now=NOW,
            )

        progress = await player_svc.record_progress(
            db,
            assignment_id=assignment_id,
            tenant_id=seed.tenant_id,
            acting_user_id=seed.user_id,
            watched_pct=50,
            now=NOW,
        )
        await db.commit()
        assert progress.quiz_unlocked is True

        attempt = await svc.start_attempt(
            db,
            assignment_id=assignment_id,
            tenant_id=seed.tenant_id,
            acting_user_id=seed.user_id,
            now=NOW,
        )
        await db.commit()
        assert attempt.attempt_number == 1

    async def test_progress_is_monotonic(self, db: AsyncSession) -> None:
        seed = await seed_course(db, min_watch_pct=0)
        assignment_id = await _assign(db, seed)
        await player_svc.record_progress(
            db,
            assignment_id=assignment_id,
            tenant_id=seed.tenant_id,
            acting_user_id=seed.user_id,
            watched_pct=60,
            now=NOW,
        )
        await db.commit()
        p = await player_svc.record_progress(
            db,
            assignment_id=assignment_id,
            tenant_id=seed.tenant_id,
            acting_user_id=seed.user_id,
            watched_pct=30,
            now=NOW,
        )
        await db.commit()
        assert p.watched_pct == 60

    async def test_manifest_reports_lock_state(self, db: AsyncSession) -> None:
        seed = await seed_course(db, min_watch_pct=50)
        assignment_id = await _assign(db, seed)
        m = await player_svc.get_player_manifest(
            db, assignment_id=assignment_id, tenant_id=seed.tenant_id, acting_user_id=seed.user_id
        )
        assert m.min_watch_pct == 50
        assert m.quiz_unlocked is False


class TestGuards:
    async def test_start_attempt_is_idempotent(self, db: AsyncSession) -> None:
        seed = await seed_course(db)
        assignment_id = await _assign(db, seed)
        a1 = await svc.start_attempt(
            db,
            assignment_id=assignment_id,
            tenant_id=seed.tenant_id,
            acting_user_id=seed.user_id,
            now=NOW,
        )
        await db.commit()
        a2 = await svc.start_attempt(
            db,
            assignment_id=assignment_id,
            tenant_id=seed.tenant_id,
            acting_user_id=seed.user_id,
            now=NOW,
        )
        await db.commit()
        assert a1.id == a2.id
        n_attempts = (
            await db.execute(
                select(func.count())
                .select_from(Attempt)
                .where(Attempt.assignment_id == assignment_id)
            )
        ).scalar_one()
        assert n_attempts == 1

    async def test_ownership_enforced(self, db: AsyncSession) -> None:
        seed = await seed_course(db)
        assignment_id = await _assign(db, seed)
        with pytest.raises(AuthorizationError):
            await svc.start_attempt(
                db,
                assignment_id=assignment_id,
                tenant_id=seed.tenant_id,
                acting_user_id=uuid.uuid4(),
                now=NOW,
            )

    async def test_submit_without_attempt_raises(self, db: AsyncSession) -> None:
        seed = await seed_course(db)
        assignment_id = await _assign(db, seed)
        with pytest.raises(InvalidStateTransitionError):
            await svc.submit_attempt(
                db,
                assignment_id=assignment_id,
                tenant_id=seed.tenant_id,
                acting_user_id=seed.user_id,
                answers={},
                attestation=_accept(),
                now=NOW,
            )

    async def test_submit_requires_attestation(self, db: AsyncSession) -> None:
        seed = await seed_course(db)
        assignment_id = await _assign(db, seed)
        await svc.start_attempt(
            db,
            assignment_id=assignment_id,
            tenant_id=seed.tenant_id,
            acting_user_id=seed.user_id,
            now=NOW,
        )
        await db.commit()
        with pytest.raises(ValidationError, match="attestation"):
            await svc.submit_attempt(
                db,
                assignment_id=assignment_id,
                tenant_id=seed.tenant_id,
                acting_user_id=seed.user_id,
                answers={},
                attestation=svc.Attestation("v1", accepted=False),
                now=NOW,
            )

    async def test_double_active_assignment_conflicts(self, db: AsyncSession) -> None:
        seed = await seed_course(db)
        await _assign(db, seed)
        with pytest.raises(ConflictError):
            await svc.create_assignment(
                db,
                tenant_id=seed.tenant_id,
                user_id=seed.user_id,
                course_id=seed.course_id,
                assigned_by_user_id=None,
                due_at=None,
                now=NOW,
            )

    async def test_cooldown_blocks_reassignment_after_pass(self, db: AsyncSession) -> None:
        seed = await seed_course(db, cooldown_days=365)
        assignment_id = await _assign(db, seed)
        await svc.start_attempt(
            db,
            assignment_id=assignment_id,
            tenant_id=seed.tenant_id,
            acting_user_id=seed.user_id,
            now=NOW,
        )
        await db.commit()
        answers = {qid: [c] for qid, (c, _w) in seed.questions.items()}
        await svc.submit_attempt(
            db,
            assignment_id=assignment_id,
            tenant_id=seed.tenant_id,
            acting_user_id=seed.user_id,
            answers=answers,
            attestation=_accept(),
            now=NOW,
        )
        await db.commit()
        with pytest.raises(CooldownActiveError):
            await svc.create_assignment(
                db,
                tenant_id=seed.tenant_id,
                user_id=seed.user_id,
                course_id=seed.course_id,
                assigned_by_user_id=None,
                due_at=None,
                now=NOW,
            )
