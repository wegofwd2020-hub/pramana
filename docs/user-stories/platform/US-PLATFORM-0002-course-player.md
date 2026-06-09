---
id: US-PLATFORM-0002
title: Course player — narrated video, watch-gate, quiz
framework: platform
domain: [compliance]
industries: [cross-industry]
persona: employee
priority: must
status: draft
also_satisfies: []
traces_to:
  - docs/api/openapi.yaml            # attempts API
  - pramana/db/models/course.py     # CourseVersion.video_asset_id, min_watch_pct
  - US-FCPA-0002
---

# US-PLATFORM-0002 — Course player — narrated video, watch-gate, quiz

## Story

> **As an** employee,
> **I want** to watch the training (narrated deck/video) and then take the quiz,
> **so that** I complete the course and earn a certificate that proves what I was
> trained on.

## Context

The player presents a **published** `CourseVersion`: its narrated deck/video (the
model already carries `video_asset_id` + `min_watch_pct`) and any animated visuals,
then the quiz. Because Pramana's product is *evidence of compliance*, the player must
**enforce the watch requirement** before unlocking the quiz and **pin completion to
the exact version**. It is framework-agnostic — the same player runs any course.

## Acceptance criteria

1. **Given** a launched course, **when** the player loads, **then** it streams the
   `CourseVersion` video/deck + animated visuals and tracks watch progress.
2. **Given** `min_watch_pct` is set, **when** the learner has not reached it, **then**
   the quiz is locked; **when** they reach it, **then** the quiz unlocks.
3. **Given** the quiz, **when** the learner submits, **then** an `Attempt` is scored
   against the pass threshold and the result (pass/fail, remaining attempts) is shown.
4. **Given** a passing attempt, **when** scoring finalizes, **then** the assignment
   moves to passed and a certificate is issued **pinned to the content version played**.
5. **Given** a learner closes mid-course, **when** they return, **then** watch
   progress resumes (no need to re-watch from zero).
6. **Given** a static-only fallback (no video), **when** the course has still-frame
   assets, **then** the player degrades gracefully to deck + captions.

## Out of scope / notes

- Video *production* (slides + animated SVG + TTS → MP4) happens in Mentible; this
  story plays whatever artifact the approved package carries.
- Accessibility (captions/transcripts) should be tracked explicitly — flagged, not
  fully specced here.

## Traceability

- `POST /assignments/{id}/attempts`, attempts API (`docs/api/openapi.yaml`).
- `CourseVersion.video_asset_id`, `min_watch_pct` (`pramana/db/models/course.py`).
- Quiz judgement content: [US-FCPA-0002](../fcpa/US-FCPA-0002-gifts-travel-hospitality-scenarios.md).
