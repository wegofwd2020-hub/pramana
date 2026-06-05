# Package Request — converting a User Story into a Mentible generation requirement

**Document type:** Authoring guide + schema for the **Pramana → Mentible** generation
request (the "definitions feed" direction of Mentible ADR-011).

> A user story is a **product capability**; a Mentible *Consumable Package* is
> **content**. You do not hand Mentible a whole story — you extract its
> *content-bearing slice* and express it as a **Package Request**. Mentible
> consumes the request + Pramana's definitions library and emits a signed package
> (ADR-011 §4), which Pramana verifies, a human approves, and Pramana publishes.

---

## 1. What converts, and what doesn't

For each acceptance criterion in a story, ask **"is this content, or is this
delivery?"**

- **Content** (→ Mentible): the lessons/modules to teach, the quiz + pass
  threshold, the clauses to cite, the audience tailoring.
- **Delivery** (→ Pramana, already specced): assignment, state machine, cooldown,
  certificates, audit log, dashboards, exports.

Only the content slice becomes a Package Request. One request may satisfy **several**
stories (shared content), and one story may need **several** requests.

## 2. Package Request schema

A Package Request is the **spec side** of the ADR-011 manifest — the inputs that
determine Mentible's output. Mentible owns the rest (`provenance`, `content_hash`,
`signature`, `package_id`/`version`).

```jsonc
{
  "request_id": "uuid",                  // stable id for this request (audit)
  "requested_by": "sme@customer",        // who authorized the generation
  "framework": "fcpa",                   // matches docs/frameworks/<framework>
  "title": "FCPA Anti-Bribery for At-Risk Roles",
  "scope": {                             // audience tailoring (tone, scenarios)
    "personas": ["employee"],
    "risk_tier": "high",                 // optional; see US-FCPA-0007
    "industries": ["cross-industry"]
  },
  "source_definitions": [                // WHAT to cover — refs into the definitions library
    { "framework": "fcpa", "clause": "anti-bribery",
      "ref": "docs/frameworks/framework_fcpa.md#anti-bribery" }
  ],
  "learning_objectives": [               // becomes modules[]
    "Recognise a 'foreign official' and 'anything of value'",
    "Spot third-party / intermediary red flags"
  ],
  "assessment": {                        // becomes quiz{}
    "required": true,
    "pass_threshold_pct": 80,
    "min_questions": 8,
    "style": "scenario-based"
  },
  "constraints": {                       // shapes module generation
    "every_claim_cited": true,           // each section cites a source clause
    "length_minutes": 20,
    "reading_level": "general-staff"
  },
  "deliverables": ["epub3", "pdf"],      // becomes artifacts[]
  "visuals": ["animated_svg"],           // becomes assets[]
  "satisfies_stories": ["US-FCPA-0001"]  // traceability back to the backlog
}
```

## 3. Request field → ADR-011 manifest field

| Package Request (input) | → Manifest (Mentible output, ADR-011 §4) |
|---|---|
| `framework`, `title` | `frameworks`, `title` |
| `source_definitions` | `source_definitions` + per-`module.citations` |
| `learning_objectives` + `constraints` | `modules[]` (deck/lessons) |
| `assessment` | `quiz { pass_threshold_pct, questions }` |
| `deliverables` | `artifacts[]` (epub3/pdf/…) |
| `visuals` | `assets[]` (animated_svg/…) |
| `scope` | tailoring of module tone/scenarios (no direct field) |
| — (Mentible decides) | `provenance`, `content_hash`, `signature`, `package_id`, `package_version` |

## 4. Prerequisite — the definitions must exist

`source_definitions[].ref` must point at a **real clause anchor** in
`docs/frameworks/<framework>.md` (Pramana owns the definitions library — ADR-011
§1). If the framework or anchor doesn't exist yet, author it first; otherwise the
package has no traceability and a reviewer (US-*-0005) can't verify content against
the regulation.

## 5. Lifecycle

```
User story (content ACs)        docs/frameworks/<framework>.md (definitions)
        └──────────────┬─────────────────┘
                       ▼
              Package Request  ──push──▶  MENTIBLE generates + signs (manifest §4)
                                                  │
            POST /consumer-library/packages  →  verify sig + content_hash
                                                  │  (fail ⇒ quarantine)
                                          RECEIVED draft  ──human approve (SoD)──▶  PUBLISHED CourseVersion
                                                                                        │
                                            the story's delivery ACs (assign/track/certify) now operate
```

The consumer half is implemented (ADR-011 PR #1): `pramana/services/consumer_library.py`,
`pramana/domain/consumable_package.py`.

## 6. Where requests live

`docs/user-stories/<framework>/briefs/PR-<FRAMEWORK>-<slug>.jsonc`, with
`satisfies_stories` linking back to the stories it serves. See
[`../fcpa/briefs/PR-FCPA-anti-bribery.jsonc`](../fcpa/briefs/PR-FCPA-anti-bribery.jsonc).
