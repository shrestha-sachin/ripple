# Ripple

**Degree plans that survive reality.**

Traditional degree planners answer *"Is this plan valid?"* Ripple answers *"Will this
plan survive contact with reality?"* Every student plan is one full section, one failed
prerequisite, or one canceled course away from a lost semester. Ripple measures how
fragile your plan is — and when something breaks, reroutes it with the fewest possible
changes while protecting your graduation date.

Built for the [Stellic Pathfinders Challenge 2026](https://www.stellic.com/pathfinders)
· Category: **Degree Planning & Discovery**

---

## The two ideas

**Ripple Score (0–100).** We sample 200 seeded disruption scenarios (course full,
course not offered, failed course, time conflict), attempt an automatic repair for each,
and report the percentage where your target graduation term still holds — alongside mean
repair cost and P(delay ≥ 1 term). Same seed, same score, every time.

**Minimum Academic Repair.** When a course becomes unavailable, the solver optimizes in
strict priority order: graduation delay → courses moved → summer/overload terms added →
excess credits. Semesters outside the disruption's downstream cone come back untouched.

## Architecture

```
Academic graph (NetworkX)
   └─> CP-SAT feasible plans (OR-Tools)
         └─> Diverse contingency plans
               └─> Monte-Carlo stress test  ──> Ripple Score + fragility ranking
                     └─> Minimum-repair rerouting
```

Three strictly separated responsibilities:

| Layer | Technology | Answers |
| --- | --- | --- |
| Dependency structure | NetworkX | What depends on what; blast radius of a disruption |
| Current facts | Supabase (Postgres) | What is true right now — catalog, rules, seats, student state |
| Feasibility & optimization | OR-Tools CP-SAT | Which plans are legal, and which repair is cheapest |

**The CP-SAT solver is the sole source of truth for feasibility.** The Claude API is used
only to phrase solver output in plain English; it never decides whether a plan is valid.

## Local setup

Requires Python 3.11–3.12 (OR-Tools has no 3.14 wheels), Node 20+, and
[uv](https://docs.astral.sh/uv/).

### Backend

```bash
cd backend
uv venv --python 3.11
uv pip install -e ".[dev]" httpx
cp .env.example .env
.venv/bin/python -m pytest -v          # verification suite
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Confirm the solver actually works on your machine:

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
```

`solver_ready: true` means CP-SAT constructed and solved a model successfully. If it is
`false`, the API reports `status: "degraded"` — fix that before building anything on top.

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev                            # http://localhost:3000
```

### Docker (mirrors production)

```bash
cd backend
docker build -t ripple-api .
docker run --rm -p 8000:8000 ripple-api
```

## Deployment

| Component | Host | Notes |
| --- | --- | --- |
| Frontend | Vercel | Set `RIPPLE_API_URL` to the backend URL |
| Backend | Render (Docker, always-on) via [`render.yaml`](render.yaml) | Set `RIPPLE_CORS_ORIGINS` to the Vercel domain |

> **OR-Tools cannot run on Vercel serverless.** The native solver binaries exceed bundle
> size and cold-start limits. The backend must run on an always-on container host.

## Demo safety

- Every solve is time-capped (plan 10s, repair 3s, scenario 0.5s). On timeout the API
  returns the best incumbent solution with `status: "TIMEOUT_BEST_EFFORT"` — the UI never
  hangs.
- `RIPPLE_OFFLINE=1` serves the local `seed/fixtures.json` instead of Supabase, so a
  network blip cannot break a live demo.
- The Ripple Score uses a fixed seed, so the number shown on stage is reproducible.

## Privacy

Ripple uses **no real student data**. All student profiles are synthetic and fictional.
Course catalog data comes from publicly published sources, documented with URLs and
access dates in [ATTRIBUTION.md](ATTRIBUTION.md).

## Build status

- [x] **Phase 0** — Deployment skeleton, CP-SAT smoke test in `/health`
- [x] **Phase 1** — Supabase schema + real catalog seed + offline fixtures
- [x] **Phase 2** — NetworkX graph + CP-SAT feasibility (oracle tests)
- [x] **Phase 3** — Vertical slice: `/plan` + semester grid UI (first demoable build)
- [x] **Phase 4** — Disruption engine + minimum repair
- [x] **Phase 5** — Ripple Score + fragility ranking
- [x] **Phase 6** — Disruption Simulator + repair animation
- [x] **Phase 7** — Submission package

## Disclosure

All tools, libraries, and AI assistants used are disclosed in [TOOLS.md](TOOLS.md), as
required by the competition rules.
