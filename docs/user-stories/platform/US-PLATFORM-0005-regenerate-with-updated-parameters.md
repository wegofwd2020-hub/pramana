---
id: US-PLATFORM-0005
title: Regenerate a draft with updated parameters
framework: platform
domain: [compliance]
industries: [cross-industry]
persona: content-author
priority: should
status: draft
also_satisfies: []
traces_to:
  - docs/user-stories/_templates/package-request.md
  - US-PLATFORM-0003
  - US-PLATFORM-0004
  - ADR-011                          # §10 re-generation versioning (open question)
---

# US-PLATFORM-0005 — Regenerate a draft with updated parameters

## Story

> **As a** content author reviewing a draft that isn't quite right,
> **I want** to tweak the original parameters and regenerate,
> **so that** I can iterate toward acceptable content without rebuilding the request
> from scratch, while keeping a clear version lineage.

## Context

This story closes the loop from **Approve** back to **Create**. When a reviewer
(US-PLATFORM-0004) finds a draft inadequate, "regenerate" re-opens the original
Package Request (US-PLATFORM-0003) pre-filled, lets them adjust parameters (e.g.
lower reading level, more scenarios, tighter citations), and re-issues it to Mentible.
Mentible returns a **new `package_version`** that supersedes the prior one.

> ⚠️ **Open design point (ADR-011 §10 "re-generation versioning"):** how a new
> `package_version` relates to an existing `CourseVersion` lineage and any in-flight
> assignments is not yet settled. This story should not silently rewrite history —
> already-published versions and existing completion records stay pinned.

## Acceptance criteria

1. **Given** a draft under review, **when** the author chooses "regenerate", **then**
   the Package Request form opens **pre-filled** with the prior request's parameters.
2. **Given** the pre-filled form, **when** the author edits parameters and submits,
   **then** a new request is pushed to Mentible and the returned package arrives as a
   **new `package_version`** that supersedes the prior draft in the queue.
3. **Given** separation of duties, **when** an author regenerates, **then** they may
   still not approve the resulting draft if they are its requester (the SoD check from
   US-PLATFORM-0004 still applies).
4. **Given** a superseded draft, **when** the new version arrives, **then** the prior
   draft is clearly marked superseded, and **any already-published `CourseVersion` and
   existing completion records remain pinned** (no history rewrite).
5. **Given** the regeneration, **when** it occurs, **then** the audit log records the
   parameter delta and the version lineage (which request produced which version).

## Out of scope / notes

- The full resolution of `package_version` → `CourseVersion` lineage + in-flight
  assignment handling is tracked as ADR-011 §10; this story implements the safe
  subset (supersede + no history rewrite) and surfaces the lineage.

## Traceability

- Request authoring: [US-PLATFORM-0003](US-PLATFORM-0003-commission-training-content.md).
- Review gate that triggers regenerate: [US-PLATFORM-0004](US-PLATFORM-0004-ingestion-review-queue.md).
- Versioning open question: **ADR-011** §10.
