# Attribution & Data Provenance

## Open-source licenses

Ripple uses the third-party packages listed in [TOOLS.md](TOOLS.md), each under its
stated license. Notable notices:

- **Google OR-Tools** — Copyright Google LLC, licensed under the Apache License 2.0.
  <https://github.com/google/or-tools/blob/main/LICENSE>
- **NetworkX** — Copyright NetworkX Developers, 3-clause BSD license.
  <https://github.com/networkx/networkx/blob/main/LICENSE.txt>
- **Next.js, React, Tailwind CSS, FastAPI, Pydantic** — MIT / BSD licenses as noted
  in TOOLS.md.

Full license texts ship with each package in the installed environment and are
reproduced in their respective upstream repositories.

## Course catalog data provenance

**Status: pending Phase 1.**

Ripple's catalog is seeded from **publicly published** university catalog pages only.
For each source, record below: institution, program, source URL, access date, and
extraction method.

| Institution | Program | Source URL | Accessed | Method |
| --- | --- | --- | --- | --- |
| Oregon State University | Computer Science B.S. (2026-2027) | https://catalog.oregonstate.edu/college-departments/engineering/school-electrical-engineering-computer-science/computer-science-bs/ | 2026-08-10 | Hand-transcribed |

### Rules we follow when sourcing catalog data

- Public catalog pages only. No authenticated pages, no scraping behind a login.
- `robots.txt` is respected. Where scraping permission is ambiguous, course data is
  **hand-transcribed** from the public catalog instead.
- Seat counts and section capacities are **plausible synthetic values**, not real
  registration data, unless a genuinely public course-schedule page is cited above.
- No institutional branding, logos, or trademarks are used. The demo does not claim
  affiliation with or endorsement by any institution.

## Student data

Every student profile in Ripple is **synthetic and fictional**, authored by the team
for demonstration. No real transcripts, student records, or personally identifiable
information of any person other than the team members appears in this project, per
Official Rules §8.
