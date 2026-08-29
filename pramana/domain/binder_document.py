"""The per-user audit binder — the sample-testing evidence package.

Each framework's §6 in ``docs/frameworks/`` lists what its regulator asks for.
Comparing them is instructive: the *per-person* package is the same document
everywhere — assignment, attempts, certificate, attestation. SOX §6.3 calls it
"sample testing", HIPAA "completion records", PCI "per-person completion
records", but the structure a reader needs is identical.

So there is one binder, and what varies per framework is framing: the citation
it answers, the regulator's own term for the artifact, and — the part worth
being careful about — **what the binder does not cover**.

That last one is deliberate. Every regulator's §6 also asks for evidence Pramana
does not hold: programme documentation, sanction policy, a material-change log.
A binder that silently omits them implies a completeness it does not have, and
an auditor discovering the gap themselves is the worse outcome. Each framing
therefore carries its own out-of-scope list, and the document ends by naming
them and saying where that evidence has to come from instead.

Pure, like the certificate document: what the binder *says* is the part with
weight, and it should be assertable without a PDF engine.
"""

from __future__ import annotations

import html
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

_DATE = "%Y-%m-%d"


@dataclass(frozen=True, slots=True)
class FrameworkFraming:
    """How one regulator frames the per-person evidence package."""

    code: str
    title: str
    #: The clause this document answers, as the regulator would cite it.
    citation: str
    #: The regulator's own term for the artifact.
    artifact_name: str
    #: Evidence this regulator asks for that Pramana does not hold.
    out_of_scope: tuple[str, ...]


#: Framings for every framework in the definitions library. Citations are taken
#: from each document's "Citable …" section, so they match what content cites.
FRAMINGS: dict[str, FrameworkFraming] = {
    "sox": FrameworkFraming(
        code="sox",
        title="SOX §404 Training Evidence Binder",
        citation="Sarbanes-Oxley §404 (ICFR); records retained per §802",
        artifact_name="sample testing evidence package",
        out_of_scope=(
            "System control documentation and auditor walkthrough",
            "Remediation status for exceptions",
        ),
    ),
    "fcpa": FrameworkFraming(
        code="fcpa",
        title="FCPA Training Evidence Binder",
        citation="FCPA internal-controls and books-and-records provisions",
        artifact_name="anti-bribery training record",
        out_of_scope=(
            "Third-party and intermediary due-diligence records",
            "Gifts, hospitality and facilitation-payment registers",
        ),
    ),
    "hipaa": FrameworkFraming(
        code="hipaa",
        title="HIPAA Workforce Training Record",
        citation="45 CFR §164.530(b) (Privacy Rule); §164.308(a)(5) (Security Rule)",
        artifact_name="workforce member completion record",
        out_of_scope=(
            "Sanction policy documentation and sanction events",
            "Material change log for policy updates",
            "PHI access classifications for the workforce roster",
        ),
    ),
    "gdpr": FrameworkFraming(
        code="gdpr",
        title="GDPR Staff Awareness Training Record",
        citation="GDPR Articles 32 and 39(1)(b) (awareness as an organisational measure)",
        artifact_name="staff awareness training record",
        out_of_scope=(
            "Records of processing activities (Article 30)",
            "DPO monitoring reports",
        ),
    ),
    "iso27001": FrameworkFraming(
        code="iso27001",
        title="ISO/IEC 27001 Competence and Awareness Evidence",
        citation="ISO/IEC 27001 Clause 7.2 (competence), Clause 7.3 and Annex A.6.3",
        artifact_name="competence and awareness evidence",
        out_of_scope=(
            "Statement of Applicability and ISMS scope",
            "Disciplinary process records (Annex A.6.4)",
            "Management review minutes",
        ),
    ),
    "pci_dss": FrameworkFraming(
        code="pci_dss",
        title="PCI DSS Security Awareness Training Record",
        citation="PCI DSS Requirement 12.6 (awareness); Requirement 6.2.2 (secure development)",
        artifact_name="in-scope personnel completion record",
        out_of_scope=(
            "CDE personnel roster and scoping documentation",
            "Awareness programme documentation",
        ),
    ),
}


@dataclass(frozen=True, slots=True)
class AttemptLine:
    """One attempt as it appears in the binder."""

    attempt_number: int
    outcome: str
    score_pct: float | None
    submitted_at: datetime | None


@dataclass(frozen=True, slots=True)
class BinderItem:
    """One assignment's evidence."""

    course_title: str
    course_version_id: uuid.UUID
    course_version_number: int
    status: str
    assigned_at: datetime | None
    terminal_at: datetime | None
    attempts: Sequence[AttemptLine]
    certificate_code: str | None
    certificate_issued_at: datetime | None
    attestation_text_version: str | None
    attestation_timestamp: datetime | None


@dataclass(frozen=True, slots=True)
class BinderDocument:
    """Everything the binder renders."""

    subject_name: str
    subject_email: str
    framing: FrameworkFraming
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    items: Sequence[BinderItem]


def _date(value: datetime | None) -> str:
    return value.strftime(_DATE) if value else "—"


def _attempts_rows(item: BinderItem) -> str:
    """Every attempt, including the failures.

    A binder showing only the passing attempt hides the retry history, which is
    exactly what sample testing is looking at.
    """
    if not item.attempts:
        return '<tr><td colspan="4">No attempts recorded.</td></tr>'
    return "".join(
        f"<tr><td>{a.attempt_number}</td><td>{html.escape(a.outcome)}</td>"
        f"<td>{a.score_pct if a.score_pct is not None else '—'}</td>"
        f"<td>{_date(a.submitted_at)}</td></tr>"
        for a in item.attempts
    )


def _item_block(item: BinderItem) -> str:
    e = html.escape
    attestation = (
        f"{e(item.attestation_text_version)} accepted {_date(item.attestation_timestamp)}"
        if item.attestation_text_version
        else "— (no certificate issued)"
    )
    certificate = (
        f"{e(item.certificate_code)} issued {_date(item.certificate_issued_at)}"
        if item.certificate_code
        else "— (not issued)"
    )
    return f"""
  <section class="item">
    <h3>{e(item.course_title)}</h3>
    <p class="version">version {item.course_version_number}
       &middot; {item.course_version_id}</p>
    <table class="facts">
      <tr><td>Status</td><td>{e(item.status)}</td></tr>
      <tr><td>Assigned</td><td>{_date(item.assigned_at)}</td></tr>
      <tr><td>Completed</td><td>{_date(item.terminal_at)}</td></tr>
      <tr><td>Certificate</td><td>{certificate}</td></tr>
      <tr><td>Attestation</td><td>{attestation}</td></tr>
    </table>
    <table class="attempts">
      <tr><th>Attempt</th><th>Outcome</th><th>Score</th><th>Submitted</th></tr>
      {_attempts_rows(item)}
    </table>
  </section>"""


def build_binder_html(doc: BinderDocument) -> str:
    """Render the binder as a self-contained HTML document."""
    e = html.escape
    f = doc.framing

    body = (
        "".join(_item_block(i) for i in doc.items)
        if doc.items
        else '<p class="empty">No training records for this person in the period shown.</p>'
    )
    gaps = "".join(f"<li>{e(g)}</li>" for g in f.out_of_scope)

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>{e(f.title)}</title>
<style>
  @page {{ size: A4; margin: 2cm; }}
  body {{ font-family: "DejaVu Sans", Helvetica, sans-serif; font-size: 10pt; color: #1a1a1a; }}
  h1 {{ font-size: 18pt; margin-bottom: 2pt; }}
  h3 {{ font-size: 12pt; margin-bottom: 0; }}
  .citation {{ color: #444; font-size: 9pt; margin-top: 0; }}
  .subject {{ margin: 16pt 0; font-size: 11pt; }}
  .version {{ color: #555; font-size: 8pt; margin-top: 2pt; }}
  .item {{ page-break-inside: avoid; border-top: 1px solid #ccc; padding-top: 10pt;
           margin-top: 14pt; }}
  table {{ border-collapse: collapse; margin-top: 6pt; }}
  .facts td {{ padding: 1pt 10pt 1pt 0; }}
  .attempts th, .attempts td {{ border: 1px solid #bbb; padding: 2pt 8pt; text-align: left; }}
  .scope {{ margin-top: 24pt; border-top: 2px solid #333; padding-top: 8pt; font-size: 9pt; }}
  .scope li {{ margin-bottom: 2pt; }}
  .empty {{ font-style: italic; margin: 24pt 0; }}
</style>
</head>
<body>
  <h1>{e(f.title)}</h1>
  <p class="citation">Responsive to {e(f.citation)} &middot;
     {e(f.artifact_name)}</p>

  <div class="subject">
    <strong>{e(doc.subject_name)}</strong> &lt;{e(doc.subject_email)}&gt;<br>
    Period {_date(doc.period_start)} to {_date(doc.period_end)} &middot;
    generated {_date(doc.generated_at)}
  </div>
{body}

  <div class="scope">
    <strong>Not covered by this binder.</strong>
    Pramana records training delivery and completion. The following evidence,
    which {e(f.code.upper())} may also require, is held outside this system and
    must be produced separately:
    <ul>{gaps}</ul>
    Records here are derived from an append-only, hash-chained audit log;
    integrity can be re-verified independently via the audit export.
  </div>
</body>
</html>
"""
