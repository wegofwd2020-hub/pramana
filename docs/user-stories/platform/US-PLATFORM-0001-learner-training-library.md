---
id: US-PLATFORM-0001
title: Learner training library ("My training")
framework: platform
domain: [compliance]
industries: [cross-industry]
persona: employee
priority: must
status: draft
also_satisfies: []
traces_to:
  - docs/api/openapi.yaml            # GET /assignments/me, GET /courses
  - US-FCPA-0001
---

# US-PLATFORM-0001 — Learner training library ("My training")

## Story

> **As an** employee,
> **I want** a single place that shows the training assigned to me and its status,
> **so that** I always know what I must complete, by when, and can launch it.

## Context

This is the learner's entry to the **Present** phase. It is framework-agnostic — the
same library shows FCPA, SOX, or any other assigned course. It distinguishes
**mandatory/assigned** training from any optional catalog, and it is the launch point
for the course player (US-PLATFORM-0002). Manager and admin roster views are related
but separate surfaces.

## Acceptance criteria

1. **Given** an authenticated employee, **when** they open "My training", **then**
   they see each assignment with title, framework tag(s), status (assigned ·
   in-progress · passed · overdue · blocked), due date, and the content version.
2. **Given** an assignment that is incomplete, **when** the employee selects it,
   **then** the course player launches for the pinned `CourseVersion`.
3. **Given** a passed assignment, **when** the employee views it, **then** they can
   access their certificate.
4. **Given** only **published** content is assignable, **when** the library renders,
   **then** drafts / unapproved content never appear to a learner.
5. **Given** an overdue or blocked assignment, **when** it is shown, **then** it is
   clearly flagged (and blocked routes the learner to the remediation path).

## Out of scope / notes

- Manager roster / completion dashboards and the auditor evidence view are separate
  stories (US-FCPA-0001 dashboard, US-FCPA-0006).
- Elective/self-enrol catalog beyond mandatory assignments is a later enhancement.

## Traceability

- `GET /assignments/me`, `GET /courses` (`docs/api/openapi.yaml`).
- Delivery of FCPA training: [US-FCPA-0001](../fcpa/US-FCPA-0001-anti-bribery-training-assignment.md).
- Launches: [US-PLATFORM-0002](US-PLATFORM-0002-course-player.md).
