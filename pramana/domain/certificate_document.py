"""The certificate document — what it says, as pure data and markup.

The PDF is a *rendering*. The `Certificate` row is the evidence, and
``GET /certificates/verify/{code}`` is what a third party should trust. Keeping
this layer pure keeps that ordering honest: the document is derived from pinned
facts and can be reproduced from them at any time, so nothing has to treat a
stored file as authoritative.

Every input is immutable — the learner's name at issue, the course *version*
tested on, the score, the issue and expiry dates, the verification code, and
which attestation text was accepted. That is what makes re-rendering safe, and
why no PDF is stored.

The one thing worth being careful about here is escaping. Course titles and
learner names are supplied by people, and they end up inside markup.
"""

from __future__ import annotations

import html
import uuid
from dataclasses import dataclass
from datetime import datetime

_DATE_FMT = "%Y-%m-%d"


@dataclass(frozen=True, slots=True)
class CertificateDocument:
    """Exactly the facts that appear on a certificate."""

    learner_name: str
    learner_email: str
    course_title: str
    course_version_id: uuid.UUID
    course_version_number: int
    score_pct: float
    issued_at: datetime
    expires_at: datetime
    verification_code: str
    attestation_text_version: str


def build_certificate_html(doc: CertificateDocument, *, now: datetime | None = None) -> str:
    """Render the certificate as a self-contained HTML page.

    Self-contained — styles inline, no external references — because the
    renderer must not depend on network access, and because the same markup
    should be openable in a browser for debugging.

    ``now`` decides only whether the document is stamped expired; it is passed in
    rather than read from the clock so the output stays a pure function of its
    inputs.
    """
    e = html.escape
    expired = now is not None and doc.expires_at <= now
    banner = (
        '<p class="expired">THIS CERTIFICATE HAS EXPIRED</p>'
        if expired
        else '<p class="valid">Valid</p>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Certificate of Completion</title>
<style>
  @page {{ size: A4 landscape; margin: 2cm; }}
  body {{ font-family: Georgia, "Times New Roman", serif; text-align: center; color: #1a1a1a; }}
  h1 {{ font-size: 34pt; margin-bottom: 0; letter-spacing: 1pt; }}
  .subtitle {{ font-size: 12pt; color: #555; margin-top: 4pt; }}
  .name {{ font-size: 26pt; margin: 28pt 0 4pt; }}
  .course {{ font-size: 18pt; margin: 18pt 0 2pt; }}
  .version {{ font-size: 10pt; color: #555; }}
  .meta {{ margin-top: 30pt; font-size: 10pt; color: #333; }}
  .meta td {{ padding: 2pt 10pt; text-align: left; }}
  .meta table {{ margin: 0 auto; }}
  .code {{ font-family: "DejaVu Sans Mono", monospace; letter-spacing: 1pt; }}
  .expired {{ color: #a00; font-weight: bold; font-size: 13pt; }}
  .valid {{ color: #060; font-size: 11pt; }}
</style>
</head>
<body>
  <h1>Certificate of Completion</h1>
  <p class="subtitle">Issued by Pramana &middot; compliance training record</p>

  <p class="name">{e(doc.learner_name)}</p>
  <p class="subtitle">{e(doc.learner_email)}</p>

  <p class="course">{e(doc.course_title)}</p>
  <p class="version">version {doc.course_version_number} &middot; {doc.course_version_id}</p>

  {banner}

  <div class="meta">
    <table>
      <tr><td>Score</td><td>{doc.score_pct}%</td></tr>
      <tr><td>Issued</td><td>{doc.issued_at.strftime(_DATE_FMT)}</td></tr>
      <tr><td>Expires</td><td>{doc.expires_at.strftime(_DATE_FMT)}</td></tr>
      <tr><td>Attestation</td><td>{e(doc.attestation_text_version)}</td></tr>
      <tr><td>Verification code</td>
          <td class="code">{e(doc.verification_code)}</td></tr>
    </table>
  </div>

  <p class="subtitle">
    Verify this certificate at /certificates/verify/{e(doc.verification_code)}
  </p>
</body>
</html>
"""
