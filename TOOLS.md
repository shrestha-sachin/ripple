# Tools & AI Disclosure

Required by Stellic Pathfinders Challenge Official Rules §6. **Failure to disclose
AI tooling is grounds for disqualification.** Update this file in the same commit
as any new dependency.

## AI assistants used

| Tool | Model | How it was used |
| --- | --- | --- |
| GitHub Copilot (agent mode) | Claude Sonnet 4.6 | Scaffolding, solver implementation, tests, UI code, reviewed and directed by the team |

## AI used *inside* the product at runtime

None. All plan generation, feasibility checking, repair optimisation, and Ripple Score computation are performed by deterministic algorithms (CP-SAT + NetworkX). No language model is called at runtime.

## Backend

| Package | Version | License | Purpose |
| --- | --- | --- | --- |
| Python | 3.11.15 | PSF-2.0 | Runtime (OR-Tools publishes no wheels for 3.14) |
| fastapi | 0.115+ | MIT | HTTP API |
| uvicorn | 0.52 | BSD-3-Clause | ASGI server |
| pydantic / pydantic-settings | 2.x | MIT | Schemas and config |
| networkx | 3.6 | BSD-3-Clause | Prerequisite dependency graph, blast-radius computation |
| ortools | 9.15 | Apache-2.0 | CP-SAT constraint solver |
| httpx | 0.27+ | BSD-3-Clause | Outbound HTTP |
| pytest | 9.x | MIT | Verification tests |

## Frontend

| Package | Version | License | Purpose |
| --- | --- | --- | --- |
| next | 16.x | MIT | App Router frontend |
| react / react-dom | 19.x | MIT | UI runtime |
| typescript | 5.x | Apache-2.0 | Types |
| tailwindcss | 4.x | MIT | Styling |
| eslint / eslint-config-next | 9.x | MIT | Linting |

Planned (not yet installed): `@xyflow/react` (React Flow, MIT) for the dependency
graph visualization; `shadcn/ui` (MIT) component primitives.

## Infrastructure

| Service | Purpose |
| --- | --- |
| Vercel | Frontend hosting |
| Render (Docker, always-on) | Backend hosting — OR-Tools native binaries cannot run on Vercel serverless |
| Supabase (Postgres) | Course catalog, degree rules, registration state, synthetic student state |
| Docker | Backend container image |
| Git / GitHub | Version control, public submission repo |

## Data

No real student data, transcripts, institutional records, or PII are used anywhere
in this project. All student profiles are synthetic and labeled as fictional.
Course catalog provenance is documented in [ATTRIBUTION.md](ATTRIBUTION.md).
