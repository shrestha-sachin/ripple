# Ripple — Submission Package

Stellic Pathfinders Challenge 2026 · Category: **Degree Planning & Discovery**

---

## Elevator pitch

Traditional degree planners answer *"Is this plan valid?"*  
Ripple answers *"Will this plan survive contact with reality?"*

Every semester, students discover that a required course is full, a prerequisite was failed, or a section they counted on wasn't offered. Existing tools show the plan as still valid — right up until it collapses. Ripple measures fragility before it matters and reroutes with the minimum possible damage when something does break.

---

## What Ripple does

### Ripple Score (0–100)
Runs 200 seeded disruption scenarios — course full, course not offered, failed course, time conflict — through the CP-SAT repair solver and reports:
- **Resilience score**: percentage of scenarios where the target graduation term still holds
- **Mean repair cost**: average number of courses moved across all scenarios
- **P(delay ≥ 1 term)**: probability of at least one semester of delay
- **Per-course fragility ranking**: which courses, if disrupted, cause the most damage

Same seed → same score → reproducible result on stage.

### Disruption Simulator
Click any course in the plan to see its **blast radius** — every downstream course that depends on it, highlighted in amber. Then pick a disruption type and fire the solver. The UI shows:
- Original plan (disrupted course in red, blast radius in amber)
- Repaired plan (moved courses in blue, any new terms highlighted)
- Summary: semesters delayed / courses moved / summer terms added

### Minimum Academic Repair
When a course becomes unavailable, the CP-SAT solver optimises in strict priority order:

1. Minimise graduation delay (weight 100 000)
2. Minimise courses moved out of their original term (weight 1 000)
3. Minimise summer / overload terms added (weight 10)
4. Minimise excess credits

Only courses in the disruption's downstream cone (blast radius) are rescheduled. Every course outside the cone stays exactly where it was.

---

## Technical summary

```
Academic graph (NetworkX)
   └─> CP-SAT feasible plans (OR-Tools)
         └─> Monte-Carlo stress test  ──> Ripple Score + fragility ranking
               └─> Minimum-repair rerouting
```

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Dependency structure | NetworkX | Prereq graph; blast-radius via `nx.descendants()` |
| Current facts | Supabase (Postgres) | Catalog, degree rules, registration state, synthetic student state |
| Feasibility & optimisation | OR-Tools CP-SAT | Which plans are legal; which repair is cheapest |

**The CP-SAT solver is the sole source of truth for feasibility.** No language model decides whether a plan is valid.

---

## Demo walkthrough

1. Open the app. Three synthetic students are preloaded:
   - **Alex** — on-track sophomore, plan solves OPTIMAL
   - **Blake** — transfer student with credit gaps, plan solves FEASIBLE
   - **Casey** — just failed CS 161 (gateway course), repair shows blast radius

2. Select **Casey**. The "Disruption Simulator" tab shows CS 161 already highlighted red with its full downstream blast radius in amber.

3. Switch to the **Ripple Score** tab and click "Run stress test". ~200 scenarios run in under a second. Casey's score will be low (fragile) because the failed gateway blocks a long prerequisite chain.

4. Select **Alex**. Switch to **Disruption Simulator**, click **CS 261** (highest-fanout course in the catalog). The amber blast radius covers most of upper-division CS. Choose "Course full" and simulate — the solver reroutes with minimal disruption.

5. Run Alex's **Ripple Score** and compare with Casey's. The score difference illustrates the core value proposition.

---

## Distinctive design decisions

**Blast radius before repair.** We show the user exactly which courses are at risk *before* asking the solver to act. This turns a black-box "your plan changed" into a transparent "here is why, and here is the minimum intervention."

**Lexicographic objective, not a weighted sum.** Graduation date is infinitely more important than which term a course lands in. Using a strict priority order in the CP-SAT objective (100 000 × delay + 1 000 × moved + 10 × summer) prevents the solver from ever trading graduation delay for a cleaner semester layout.

**Deterministic stress test.** Fixed seed (20260810) means the Ripple Score shown on stage can be independently verified and is the same number every time.

**Demo safety.** `RIPPLE_OFFLINE=1` serves `seed/fixtures.json` instead of Supabase. Every solve is time-capped. The API returns the best incumbent on timeout — the UI never hangs.

---

## Running the demo locally

```bash
# Backend
cd backend
uv venv --python 3.11
uv pip install -e ".[dev]" httpx
cp .env.example .env
# Set RIPPLE_OFFLINE=true in .env to skip Supabase entirely
.venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
cp .env.local.example .env.local
npm run dev    # http://localhost:3000
```

Confirm the solver works:
```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
# "solver_ready": true  ← required
```

Run the full test suite (125 tests, ~7s):
```bash
cd backend && .venv/bin/python -m pytest -v
```

---

## Data & privacy

- **No real student data.** All three student profiles are synthetic and fictional, authored by the team.
- **Course catalog** is hand-transcribed from the publicly published Oregon State University 2026-2027 catalog. Full provenance in [ATTRIBUTION.md](ATTRIBUTION.md).
- **No PII.** No authentication, no tracking, no real registration data.

---

## Files

| File | Purpose |
| --- | --- |
| [README.md](README.md) | Architecture, local setup, deployment |
| [TOOLS.md](TOOLS.md) | All tools and AI assistants disclosed per §6 |
| [ATTRIBUTION.md](ATTRIBUTION.md) | Data provenance per §8 |
| `backend/` | FastAPI + OR-Tools + NetworkX |
| `frontend/` | Next.js 16 + TypeScript + Tailwind |
| `render.yaml` | One-click Render deploy |
