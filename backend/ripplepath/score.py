"""Ripple Score — Monte-Carlo stress test engine.

Phase 5 delivers the product's headline metric: a single 0–100 score that
answers "how likely is your current plan to survive contact with reality?"

**Algorithm**
1. Generate ``n_scenarios`` disruption scenarios using a fixed RNG seed.
   Every run with the same seed produces the same score — this is what lets
   us say "Ripple Score: 72" on stage and have it mean something.
2. For each scenario, call ``repair_plan()`` with a tight per-scenario timeout.
3. Aggregate:
   - Ripple Score = 100 × (scenarios where graduation_delay == 0) / total
   - P(delay ≥ 1 term) = scenarios with delay ≥ 1 / total
   - Mean courses moved over feasible scenarios
   - Per-course fragility: how often disrupting a course caused a delay

**Disruption weights**
   COURSE_FULL 40 %, NOT_OFFERED 30 %, FAILED_COURSE 20 %, TIME_CONFLICT 10 %

These weights are deliberately conservative. Real disruptions skew toward
seat shortages, so COURSE_FULL is the most common scenario.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ripplepath.graph import blast_radius, build_graph
from ripplepath.models import Catalog, Disruption
from ripplepath.solver import SolveStatus, repair_plan

if TYPE_CHECKING:
    pass


# Disruption kind sampling weights (must sum to 100 for readability).
_KIND_WEIGHTS = {
    "COURSE_FULL": 40,
    "NOT_OFFERED": 30,
    "FAILED_COURSE": 20,
    "TIME_CONFLICT": 10,
}
_KINDS = list(_KIND_WEIGHTS.keys())
_WEIGHTS = list(_KIND_WEIGHTS.values())


@dataclass
class ScenarioResult:
    """Result of a single stress-test scenario."""

    scenario_index: int
    disruption_kind: str
    disrupted_course: str
    disruption_term: str | None
    repair_status: str
    graduation_delay: int
    courses_moved: int
    summer_terms_added: int
    affected_course_count: int
    solver_wall_time: float

    @property
    def on_time(self) -> bool:
        """True if the repair kept the original graduation term."""
        return self.graduation_delay == 0 and self.repair_status in (
            SolveStatus.OPTIMAL,
            SolveStatus.FEASIBLE,
            SolveStatus.TIMEOUT_BEST_EFFORT,
        )

    @property
    def is_feasible(self) -> bool:
        return self.repair_status in (
            SolveStatus.OPTIMAL,
            SolveStatus.FEASIBLE,
            SolveStatus.TIMEOUT_BEST_EFFORT,
        )


@dataclass
class CourseFragility:
    """Fragility stats for a single course."""

    course_id: str
    title: str
    disruption_count: int
    """How many scenarios disrupted this course."""
    delay_count: int
    """How many of those caused a graduation delay."""
    delay_rate: float
    """delay_count / disruption_count."""
    blast_size: int
    """Number of other courses in this course's downstream cone."""


@dataclass
class RippleScore:
    """Aggregated result of the Monte-Carlo stress test."""

    student_id: str
    score: int
    """0–100: percentage of scenarios where graduation term was preserved."""
    scenario_count: int
    """Total scenarios run (may be < requested if timeout hit)."""
    on_time_count: int
    """Scenarios where graduation_delay == 0 and repair was feasible."""
    infeasible_count: int
    """Scenarios where no repair was possible."""
    delay_probability: float
    """P(graduation_delay ≥ 1 term) over all scenarios."""
    mean_courses_moved: float
    """Mean courses moved per feasible scenario."""
    mean_graduation_delay: float
    """Mean graduation delay (in terms) over all scenarios."""
    course_fragility: list[CourseFragility]
    """Courses ranked by delay_rate descending (top fragile courses first)."""
    scenarios: list[ScenarioResult]
    """All individual scenario results (for frontend animation in Phase 6)."""
    rng_seed: int
    total_wall_time: float


def compute_ripple_score(
    catalog: Catalog,
    student_id: str,
    base_schedule: dict[str, str],
    n_scenarios: int = 200,
    seed: int = 20260810,
    scenario_timeout: float = 0.5,
    total_timeout: float = 120.0,
) -> RippleScore:
    """Run the Monte-Carlo stress test and return a Ripple Score.

    Args:
        catalog: The complete data layer snapshot.
        student_id: Student whose plan is being stress-tested.
        base_schedule: The pre-disruption schedule (course_id -> term).
        n_scenarios: Number of disruption scenarios to simulate.
        seed: RNG seed. Same seed → same score on every run.
        scenario_timeout: Max solver time per scenario in seconds.
        total_timeout: Hard wall-time cap for the entire stress test.

    Returns:
        RippleScore with aggregated stats and per-course fragility.
    """
    started_at = time.monotonic()

    graph = build_graph(catalog)
    courses = catalog.course_map()
    scheduled_courses = [c for c in base_schedule if c in courses]

    if not scheduled_courses:
        return _empty_score(student_id, seed)

    rng = random.Random(seed)
    scenarios: list[ScenarioResult] = []

    # Pre-compute blast radii to use in scenario generation.
    blast_cache: dict[str, set[str]] = {}
    for course_id in scheduled_courses:
        try:
            blast_cache[course_id] = blast_radius(graph, course_id)
        except KeyError:
            blast_cache[course_id] = set()

    for i in range(n_scenarios):
        # Hard wall-time guard.
        if time.monotonic() - started_at > total_timeout:
            break

        # Sample a disruption.
        course_id = rng.choice(scheduled_courses)
        term = base_schedule[course_id]
        kind = rng.choices(_KINDS, weights=_WEIGHTS, k=1)[0]

        disruption = Disruption(
            kind=kind,  # type: ignore[arg-type]
            course_id=course_id,
            term=None if kind == "FAILED_COURSE" else term,
        )

        result = repair_plan(
            catalog=catalog,
            student_id=student_id,
            original_schedule=base_schedule,
            disruption=disruption,
            timeout_seconds=scenario_timeout,
        )

        affected_in_plan = len(
            (blast_cache.get(course_id, set()) | {course_id}) & set(base_schedule)
        )

        scenarios.append(
            ScenarioResult(
                scenario_index=i,
                disruption_kind=kind,
                disrupted_course=course_id,
                disruption_term=disruption.term,
                repair_status=result.status.value,
                graduation_delay=result.graduation_delay,
                courses_moved=result.courses_moved,
                summer_terms_added=result.summer_terms_added,
                affected_course_count=affected_in_plan,
                solver_wall_time=result.solver_wall_time,
            )
        )

    total_wall_time = time.monotonic() - started_at
    n_run = len(scenarios)

    if n_run == 0:
        return _empty_score(student_id, seed)

    on_time = [s for s in scenarios if s.on_time]
    feasible = [s for s in scenarios if s.is_feasible]
    delayed = [s for s in scenarios if s.is_feasible and s.graduation_delay >= 1]
    infeasible = [s for s in scenarios if not s.is_feasible]

    score = round(100 * len(on_time) / n_run)
    delay_prob = len(delayed) / n_run
    mean_moved = (
        sum(s.courses_moved for s in feasible) / len(feasible) if feasible else 0.0
    )
    mean_delay = sum(s.graduation_delay for s in scenarios) / n_run

    # Per-course fragility.
    per_course: dict[str, dict] = {}
    for s in scenarios:
        cid = s.disrupted_course
        if cid not in per_course:
            per_course[cid] = {"disruption_count": 0, "delay_count": 0}
        per_course[cid]["disruption_count"] += 1
        if s.graduation_delay >= 1 or not s.is_feasible:
            per_course[cid]["delay_count"] += 1

    fragility: list[CourseFragility] = []
    for cid, stats in per_course.items():
        dc = stats["disruption_count"]
        dlc = stats["delay_count"]
        course = courses.get(cid)
        fragility.append(
            CourseFragility(
                course_id=cid,
                title=course.title if course else cid,
                disruption_count=dc,
                delay_count=dlc,
                delay_rate=dlc / dc if dc else 0.0,
                blast_size=len(blast_cache.get(cid, set())),
            )
        )

    # Sort by delay_rate desc, then blast_size desc.
    fragility.sort(key=lambda c: (-c.delay_rate, -c.blast_size))

    return RippleScore(
        student_id=student_id,
        score=score,
        scenario_count=n_run,
        on_time_count=len(on_time),
        infeasible_count=len(infeasible),
        delay_probability=round(delay_prob, 4),
        mean_courses_moved=round(mean_moved, 2),
        mean_graduation_delay=round(mean_delay, 3),
        course_fragility=fragility,
        scenarios=scenarios,
        rng_seed=seed,
        total_wall_time=round(total_wall_time, 3),
    )


def _empty_score(student_id: str, seed: int) -> RippleScore:
    return RippleScore(
        student_id=student_id,
        score=0,
        scenario_count=0,
        on_time_count=0,
        infeasible_count=0,
        delay_probability=0.0,
        mean_courses_moved=0.0,
        mean_graduation_delay=0.0,
        course_fragility=[],
        scenarios=[],
        rng_seed=seed,
        total_wall_time=0.0,
    )
