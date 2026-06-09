# Platform — cross-cutting product surfaces (Epic)

**Category code:** `PLATFORM` (not a regulation — a **framework-agnostic** product capability)
**Domain(s):** compliance (serves every framework)
**Status:** 🚧 In progress

> These stories describe the **product chassis** that every framework rides on. A
> framework folder (e.g. [`fcpa/`](../fcpa/README.md)) says *what content* a
> regulation needs; the platform stories say *how the product creates, manufactures,
> approves, and presents* that content — once, for all frameworks.

---

## 1. Why a platform category

The four phases of the [mental model](../README.md#mental-model--create--manufacture--approve--present) are
realized by surfaces that are **the same regardless of regulation**:

| Phase | Surface | Persona | Story |
|---|---|---|---|
| **Create** | Commission content from a law (Package Request → Mentible) | content-author | [US-PLATFORM-0003](US-PLATFORM-0003-commission-training-content.md) |
| **Manufacture** | _(Mentible — external; ADR-011)_ | — | — |
| **Approve** | Ingestion review & approval queue | content-author | [US-PLATFORM-0004](US-PLATFORM-0004-ingestion-review-queue.md) |
| **Approve** | Regenerate a draft with updated parameters | content-author | [US-PLATFORM-0005](US-PLATFORM-0005-regenerate-with-updated-parameters.md) |
| **Present** | Learner training library ("My training") | employee | [US-PLATFORM-0001](US-PLATFORM-0001-learner-training-library.md) |
| **Present** | Course player (narrated video + watch-gate + quiz) | employee | [US-PLATFORM-0002](US-PLATFORM-0002-course-player.md) |

Each framework's stories (e.g. FCPA) **reuse** these surfaces; the framework only
supplies the content and the targeting rules.

## 2. Story index

| ID | Title | Phase | Persona | Priority | Status |
|---|---|---|---|---|---|
| [US-PLATFORM-0001](US-PLATFORM-0001-learner-training-library.md) | Learner training library ("My training") | Present | employee | must | draft |
| [US-PLATFORM-0002](US-PLATFORM-0002-course-player.md) | Course player — narrated video, watch-gate, quiz | Present | employee | must | draft |
| [US-PLATFORM-0003](US-PLATFORM-0003-commission-training-content.md) | Commission training content from a regulation | Create | content-author | must | draft |
| [US-PLATFORM-0004](US-PLATFORM-0004-ingestion-review-queue.md) | Ingestion review & approval queue | Approve | content-author | must | draft |
| [US-PLATFORM-0005](US-PLATFORM-0005-regenerate-with-updated-parameters.md) | Regenerate a draft with updated parameters | Approve→Create | content-author | should | draft |

## 3. Traceability

- Mental model & boundaries: [`../README.md`](../README.md), Mentible **ADR-011**.
- Approval policy & state machine: `docs/03_ai_drafted_human_approved_content.md`,
  `pramana/domain/content_approval.py`.
- Package Request contract: [`../_templates/package-request.md`](../_templates/package-request.md).
- These surfaces are exercised by every framework backlog (first: [`../fcpa/`](../fcpa/README.md)).
