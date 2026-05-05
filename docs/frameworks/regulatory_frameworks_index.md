# Regulatory Frameworks — Index

**Document type:** Master index for compliance training framework references
**Purpose:** Map each supported (or candidate) framework to its standalone reference doc, surface overlaps and conflicts, and guide framework-selection decisions for future phases.

> ⚠️ **Disclaimer:** These documents are engineering references describing how the compliance training system should be designed to *support* each framework. They are not legal advice. Regulatory interpretation must be confirmed with John Thomas Corporate's compliance counsel before any framework becomes a binding commitment.

---

## 1. Why Multiple Frameworks?

A compliance training and tracking system rarely supports just one regulatory framework. Most enterprise customers operate under several simultaneously — a healthcare-adjacent fintech could need SOX (financial reporting) + HIPAA (PHI) + PCI DSS (card data) + ISO 27001 (security) all at once. The training system's job is to let the customer demonstrate **training-related compliance** with each.

This index helps decide which framework support to prioritize and surfaces design tensions between them.

---

## 2. Framework Reference Documents

| Framework | Status (v1) | Document |
|---|---|---|
| **SOX (Sarbanes-Oxley)** | ✅ In scope for v1 | `framework_sox.md` |
| **HIPAA** | ⏳ Future phase | `framework_hipaa.md` |
| **GDPR** | ⏳ Future phase | `framework_gdpr.md` |
| **ISO 27001** | ⏳ Future phase | `framework_iso27001.md` |
| **PCI DSS** | ⏳ Future phase | `framework_pci_dss.md` |

Each document follows an identical structure for ease of comparison:
1. Framework overview
2. Why it matters for compliance training systems
3. Training requirements imposed by the framework
4. System design implications
5. Data model implications
6. Audit trail and evidence requirements
7. Retention requirements
8. User rights and access controls
9. Conflicts with other frameworks
10. Implementation checklist

---

## 3. When Each Framework Applies

| Framework | Applies When… |
|---|---|
| **SOX** | Customer is a US public company or files with the SEC. Training is required to demonstrate Section 404 internal controls. |
| **HIPAA** | Customer is a Covered Entity (healthcare provider, health plan, clearinghouse) or a Business Associate handling PHI. |
| **GDPR** | Customer processes personal data of EU/EEA residents, regardless of where the customer is located. |
| **ISO 27001** | Customer is pursuing or maintains ISO 27001 certification. Often a contractual requirement for B2B customers. |
| **PCI DSS** | Customer stores, processes, or transmits payment card data. |

---

## 4. Framework Overlap Matrix

Many requirements appear in multiple frameworks. Building once for the strictest requirement satisfies the others.

| Capability | SOX | HIPAA | GDPR | ISO 27001 | PCI DSS |
|---|:---:|:---:|:---:|:---:|:---:|
| Annual training cadence | ✅ | ✅ | ✅ | ✅ | ✅ |
| User attestation on completion | ✅ | ✅ | ✅ | ✅ | ✅ |
| Training records retention | 7 yr | 6 yr | varies | 3 yr+ | 1 yr+ |
| Tamper-evident audit log | ✅ | ✅ | ✅ | ✅ | ✅ |
| Role-based training paths | ✅ | ✅ | ⚠️ | ✅ | ✅ |
| External auditor read access | ✅ | ✅ | ✅ | ✅ | ✅ |
| User-deletion / right to erasure | ❌ | ⚠️ | ✅ | ⚠️ | ❌ |
| Breach notification training | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| Training record export | ✅ | ✅ | ✅ | ✅ | ✅ |

✅ = Required · ⚠️ = Best practice / partial · ❌ = Not specifically required

---

## 5. Key Design Tensions Between Frameworks

### 5.1 Retention vs. Right to Erasure

- **SOX / HIPAA / PCI DSS / ISO 27001** all require retaining training records for years.
- **GDPR** Article 17 grants individuals the right to erase personal data.

**Resolution:** Pseudonymization on departure or erasure request — retain records linked to a synthetic `user_id`, replace PII (`email`, `first_name`, `last_name`) with hashed/null values. GDPR Article 17(3)(b) allows retention when needed for compliance with a legal obligation, which covers SOX/HIPAA-mandated retention. This pattern is already baked into the v1 data model.

### 5.2 Training Cadence Differences

- **SOX, ISO 27001, PCI DSS, HIPAA** all default to annual.
- **HIPAA** also requires training "within a reasonable time" of hire and after policy changes.
- **GDPR** has no fixed cadence but Article 39 requires DPO to monitor it.

**Resolution:** Per-course `cooldown_days` (already in v1) plus optional `assignment_triggers` table for v2 (on-hire, on-role-change, on-policy-update).

### 5.3 Cross-Border Transfer

- **GDPR** restricts transfer of EU personal data outside the EEA.
- **HIPAA** has no equivalent restriction but does require Business Associate Agreements.

**Resolution:** Future regional data-residency option for the platform (e.g., EU-only deployment). Not in v1 scope.

### 5.4 Auditor vs. Regulator Access

- **SOX** auditors are external CPA firms with read access to evidence.
- **HIPAA / PCI DSS** investigators are regulators (HHS OCR, card brands) with broader investigative powers.
- **ISO 27001** auditors are certification body assessors.

**Resolution:** A single `Auditor` role with read access and CSV/PDF export covers all four use cases. Different audit-binder export templates per framework can be added in later phases.

---

## 6. Recommended Framework Roadmap

Based on typical corporate-training-system buyer patterns:

| Phase | Frameworks added | Rationale |
|---|---|---|
| **v1** | SOX | Confirmed scope for John Thomas Corporate |
| **v2** | + HIPAA | Healthcare adjacency is the most common second framework for US enterprise buyers |
| **v3** | + ISO 27001 | Security certification is a frequent enterprise procurement gate |
| **v4** | + GDPR | Triggered when first EU customer or operation appears |
| **v5** | + PCI DSS | Triggered when payment-handling employees are in scope |

This is a recommendation, not a commitment — actual sequencing should follow customer demand.

---

## 7. How to Use the Individual Framework Docs

Each framework doc is intended to be read in two scenarios:

1. **Before adding the framework to the roadmap.** The "System design implications" and "Data model implications" sections indicate the engineering cost.
2. **During an audit or compliance review.** The "Audit trail and evidence requirements" and "Implementation checklist" sections answer "are we covered?"

---

*End of index.*
