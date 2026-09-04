"""Consumer-facing router: my packages, lesson list, views, and quiz."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.api.dependencies import (
    get_asset_signer,
    get_db_session,
    get_principal,
    require_course_entitlement,
)
from pramana.api.schemas import (
    EndViewIn,
    LessonListItemOut,
    MyPackageOut,
    PlaySessionOut,
    QuizFormOut,
    QuizOptionOut,
    QuizQuestionOut,
    QuizResultOut,
    StartViewIn,
    SubmitQuizIn,
)
from pramana.db.models.consumer import (
    Enrollment,
    Entitlement,
    Package,
    PackageCourse,
)
from pramana.db.models.course import Course
from pramana.domain.assignment_state import utcnow
from pramana.services.auth import Principal
from pramana.services.consumer import entitlements as ent
from pramana.services.consumer import play, quiz
from pramana.services.player import AssetUrlSigner

router = APIRouter(tags=["consumer"])

Session = Annotated[AsyncSession, Depends(get_db_session)]
Caller = Annotated[Principal, Depends(get_principal)]
Gated = Annotated[Principal, Depends(require_course_entitlement)]


@router.get("/me/packages", response_model=list[MyPackageOut])
async def my_packages(session: Session, caller: Caller) -> list[MyPackageOut]:
    rows = (
        await session.execute(
            select(Package)
            .join(Entitlement, Entitlement.package_id == Package.id)
            .where(Entitlement.user_id == caller.user_id, Entitlement.status == "active")
        )
    ).scalars()
    return [MyPackageOut.model_validate(p) for p in rows]


@router.get("/packages/{package_id}/lessons", response_model=list[LessonListItemOut])
async def package_lessons(
    package_id: uuid.UUID, session: Session, caller: Caller
) -> list[LessonListItemOut]:
    # Access: caller must hold an active entitlement for THIS package.
    held = (
        await session.execute(
            select(Entitlement.id).where(
                Entitlement.user_id == caller.user_id,
                Entitlement.package_id == package_id,
                Entitlement.status == "active",
            )
        )
    ).scalar_one_or_none()
    if held is None:
        from pramana.exceptions import EntitlementRequiredError

        raise EntitlementRequiredError(
            "no entitlement for this package",
            context={"package_id": str(package_id)},
        )

    rows = (
        await session.execute(
            select(Course, PackageCourse.display_order)
            .join(PackageCourse, PackageCourse.course_id == Course.id)
            .where(PackageCourse.package_id == package_id)
            .order_by(PackageCourse.display_order)
        )
    ).all()
    enrollments = {
        e.course_id: e
        for e in (
            await session.execute(select(Enrollment).where(Enrollment.user_id == caller.user_id))
        ).scalars()
    }
    out: list[LessonListItemOut] = []
    for course, order in rows:
        e = enrollments.get(course.id)
        out.append(
            LessonListItemOut(
                course_id=course.id,
                title=course.title,
                display_order=order,
                view_count=e.view_count if e else 0,
                completion_count=e.completion_count if e else 0,
                best_score_pct=e.best_score_pct if e else None,
            )
        )
    return out


@router.post(
    "/lessons/{course_id}/views",
    response_model=PlaySessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def start_view(
    course_id: uuid.UUID,
    body: StartViewIn,
    session: Session,
    caller: Gated,
    sign_asset: Annotated[AssetUrlSigner, Depends(get_asset_signer)],
) -> PlaySessionOut:
    tenant_id = await ent.get_consumer_tenant_id(session)
    entitlement_id = await _active_entitlement_id_for_course(session, caller.user_id, course_id)
    manifest = await play.start_view(
        session,
        tenant_id=tenant_id,
        user_id=caller.user_id,
        course_id=course_id,
        entitlement_id=entitlement_id,
        media_kind=body.media_kind,
        now=utcnow(),
        sign_asset=sign_asset,
    )
    return PlaySessionOut(
        play_session_id=manifest.play_session_id,
        course_version_id=manifest.course_version_id,
        media_url=manifest.media_url,
        media_kind=manifest.media_kind,
        min_watch_pct=manifest.min_watch_pct,
    )


@router.post(
    "/lessons/{course_id}/views/{play_session_id}/end",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def end_view(
    course_id: uuid.UUID,
    play_session_id: uuid.UUID,
    body: EndViewIn,
    session: Session,
    caller: Gated,
) -> Response:
    tenant_id = await ent.get_consumer_tenant_id(session)
    await play.end_view(
        session,
        tenant_id=tenant_id,
        user_id=caller.user_id,
        play_session_id=play_session_id,
        duration_seconds=body.duration_seconds,
        max_watched_pct=body.max_watched_pct,
        now=utcnow(),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/lessons/{course_id}/quiz/start",
    response_model=QuizFormOut,
    status_code=status.HTTP_201_CREATED,
)
async def start_quiz(course_id: uuid.UUID, session: Session, caller: Gated) -> QuizFormOut:
    tenant_id = await ent.get_consumer_tenant_id(session)
    entitlement_id = await _active_entitlement_id_for_course(session, caller.user_id, course_id)
    form = await quiz.start_quiz(
        session,
        tenant_id=tenant_id,
        user_id=caller.user_id,
        course_id=course_id,
        entitlement_id=entitlement_id,
        now=utcnow(),
    )
    return QuizFormOut(
        attempt_id=form.attempt_id,
        course_version_id=form.course_version_id,
        questions=[
            QuizQuestionOut(
                question_id=q.question_id,
                question_text=q.question_text,
                question_type=q.question_type,
                options=[
                    QuizOptionOut(option_id=o.option_id, option_text=o.option_text)
                    for o in q.options
                ],
            )
            for q in form.questions
        ],
    )


@router.post("/lessons/{course_id}/quiz/{attempt_id}/submit", response_model=QuizResultOut)
async def submit_quiz(
    course_id: uuid.UUID,
    attempt_id: uuid.UUID,
    body: SubmitQuizIn,
    session: Session,
    caller: Gated,
) -> QuizResultOut:
    tenant_id = await ent.get_consumer_tenant_id(session)
    result = await quiz.submit_quiz(
        session,
        tenant_id=tenant_id,
        user_id=caller.user_id,
        attempt_id=attempt_id,
        answers=body.answers,
        now=utcnow(),
    )
    return QuizResultOut(
        attempt_id=result.attempt_id,
        score_pct=result.score_pct,
        is_all_correct=result.is_all_correct,
        correct_count=result.correct_count,
        question_count=result.question_count,
    )


async def _active_entitlement_id_for_course(
    session: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID
) -> uuid.UUID:
    return (
        await session.execute(
            select(Entitlement.id)
            .join(PackageCourse, PackageCourse.package_id == Entitlement.package_id)
            .where(
                Entitlement.user_id == user_id,
                Entitlement.status == "active",
                PackageCourse.course_id == course_id,
            )
            .limit(1)
        )
    ).scalar_one()
