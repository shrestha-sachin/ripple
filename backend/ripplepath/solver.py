"""CP-SAT feasibility solver.

This is the **sole source of truth** for whether a degree plan is achievable.
The solver answers two questions:

1. **Feasibility**: Can this student graduate by the target term?
2. **Planning**: If yes, produce a concrete schedule.

The solver knows about:
- Prerequisite chains (including OR-groups)
- Term offerings (season-based)
- Credit limits per term
- Degree requirements (n_of_m with min credits)

It does NOT know about seat availability or disruptions - those are Phase 4-5
concerns layered on top of this base feasibility engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

import networkx as nx
from ortools.sat.python import cp_model

from ripplepath.graph import build_graph, degree_relevant_courses, earliest_feasible_index
from ripplepath.models import Catalog, DegreeRequirement, Disruption, StudentState, terms_between


class SolveStatus(str, Enum):
    """Outcome of a solve attempt."""

    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    TIMEOUT_BEST_EFFORT = "TIMEOUT_BEST_EFFORT"
    TIMEOUT_NO_SOLUTION = "TIMEOUT_NO_SOLUTION"
    ERROR = "ERROR"


@dataclass
class SolveResult:
    """Result of a feasibility check or planning solve."""

    status: SolveStatus
    schedule: dict[str, str] = field(default_factory=dict)
    """course_id -> term if feasible, else empty."""
    graduation_term: str | None = None
    """Actual graduation term achieved, may be earlier than target."""
    solver_wall_time: float = 0.0
    """Wall-clock seconds spent in the solver."""
    message: str = ""
    """Human-readable status message."""

    @property
    def is_feasible(self) -> bool:
        return self.status in (
            SolveStatus.OPTIMAL,
            SolveStatus.FEASIBLE,
            SolveStatus.TIMEOUT_BEST_EFFORT,
        )


def check_feasibility(
    catalog: Catalog,
    student_id: str,
    timeout_seconds: float = 10.0,
) -> SolveResult:
    """Check if the student can graduate by their target term.

    This is the fast path for the Ripple Score: we only need a yes/no answer,
    not a pretty schedule.
    """
    return solve_plan(
        catalog=catalog,
        student_id=student_id,
        timeout_seconds=timeout_seconds,
        optimization_mode="feasibility",
    )


def solve_plan(
    catalog: Catalog,
    student_id: str,
    timeout_seconds: float = 10.0,
    optimization_mode: Literal["feasibility", "balanced"] = "balanced",
) -> SolveResult:
    """Build and solve a CP-SAT model for degree planning.

    Args:
        catalog: The complete data layer snapshot.
        student_id: Synthetic student to plan for.
        timeout_seconds: Max wall-clock time for the solver.
        optimization_mode: "feasibility" returns any valid plan fast;
            "balanced" optimizes for earlier graduation and lighter terms.

    Returns:
        SolveResult with status, schedule, and timing information.
    """
    try:
        student = catalog.student(student_id)
    except KeyError as e:
        return SolveResult(
            status=SolveStatus.ERROR,
            message=str(e),
        )

    # Build prerequisite graph.
    graph = build_graph(catalog)

    # Restrict to degree-relevant courses (scale guard).
    try:
        relevant = degree_relevant_courses(catalog, graph, student.program)
    except Exception as e:
        return SolveResult(
            status=SolveStatus.ERROR,
            message=f"cannot determine degree-relevant courses: {e}",
        )

    # Planning horizon - use full horizon to target, capped at 16 for tractability.
    # The default 12-term cap in planning_terms is too tight for some personas.
    terms = terms_between(student.current_term, student.target_graduation_term)
    if not terms:
        return SolveResult(
            status=SolveStatus.INFEASIBLE,
            message="no planning terms available (current >= target graduation)",
        )
    # Cap at 16 terms (4 years) to keep the model tractable.
    terms = terms[:16]

    # Courses the student still needs to take.
    completed = set(student.completed_courses)
    remaining = relevant - completed

    # Earliest term index for each course (combines chain depth + offerings).
    course_earliest = earliest_feasible_index(catalog, graph, completed, terms)

    # Courses that cannot be scheduled at all within the horizon.
    unschedulable = remaining - set(course_earliest.keys())

    # Build the model.
    model = cp_model.CpModel()
    courses = catalog.course_map()

    # Decision variables: X[c][t] = 1 iff course c is taken in term t.
    X: dict[str, dict[int, cp_model.IntVar]] = {}
    for course_id in remaining:
        if course_id in unschedulable:
            continue
        course = courses[course_id]
        earliest = course_earliest.get(course_id, 0)
        X[course_id] = {}
        for t_idx, term in enumerate(terms):
            if t_idx < earliest:
                continue  # Provably too early.
            if not course.offered_in(term):
                continue  # Not offered this season.
            X[course_id][t_idx] = model.NewBoolVar(f"X_{course_id}_{t_idx}")

    # If any required course has no valid term slots, infeasible.
    requirements = catalog.requirements_for(student.program)
    for req in requirements:
        # Check if at least n_of_m eligible courses can be scheduled.
        schedulable = [c for c in req.eligible_courses if c in X or c in completed]
        if len(schedulable) < req.n_of_m:
            return SolveResult(
                status=SolveStatus.INFEASIBLE,
                message=f"requirement {req.requirement_id!r} needs {req.n_of_m} "
                f"courses but only {len(schedulable)} are schedulable",
            )

    # Constraint 1: Each course is taken AT MOST once.
    # Degree requirements (constraint 5) enforce which courses MUST be taken.
    # Elective courses are optional - we don't force them all.
    for course_id, term_vars in X.items():
        if term_vars:
            model.AddAtMostOne(term_vars.values())

    # Constraint 2: Prerequisites must complete before dependents.
    # "Completion term" means the term index where the course is taken.
    # The dependent must be taken in a strictly later term.
    for course_id in X:
        for prereq_id in graph.predecessors(course_id):
            if prereq_id in completed:
                continue  # Already done.
            if prereq_id not in X:
                # Prereq is unschedulable but required - should have been caught above.
                continue

            # For each term t where course_id might be taken,
            # all prereq assignments must be in earlier terms.
            for t_dep, var_dep in X[course_id].items():
                prereq_before = []
                for t_pre in X[prereq_id]:
                    if t_pre < t_dep:
                        prereq_before.append(X[prereq_id][t_pre])
                # If we assign dependent to t_dep, prereq must be in some earlier term.
                if prereq_before:
                    model.Add(sum(prereq_before) >= 1).OnlyEnforceIf(var_dep)
                else:
                    # No earlier term is feasible for prereq -> can't take dependent here.
                    model.Add(var_dep == 0)

    # Constraint 3: OR-group prerequisites.
    # Within an OR-group, at least one must be completed before the dependent.
    prereq_groups: dict[str, dict[str, list[str]]] = {}
    for row in catalog.prerequisites:
        if row.course_id not in X:
            continue
        key = (row.course_id, row.group_id)
        prereq_groups.setdefault(row.course_id, {}).setdefault(row.group_id, []).append(
            row.requires_course_id
        )

    for course_id, groups in prereq_groups.items():
        for group_id, members in groups.items():
            # Check if any member is already completed.
            if any(m in completed for m in members):
                continue  # Group satisfied.

            # At least one member must be taken before course_id.
            for t_dep, var_dep in X[course_id].items():
                any_prereq_before = []
                for prereq_id in members:
                    if prereq_id in completed:
                        continue  # This path is always satisfied.
                    if prereq_id not in X:
                        continue
                    for t_pre in X[prereq_id]:
                        if t_pre < t_dep:
                            any_prereq_before.append(X[prereq_id][t_pre])
                if any_prereq_before:
                    model.Add(sum(any_prereq_before) >= 1).OnlyEnforceIf(var_dep)
                elif not any(m in completed for m in members):
                    # No valid prereq placement and none completed -> can't use this slot.
                    model.Add(var_dep == 0)

    # Constraint 4: Credit limits per term (max only).
    # We enforce max_term_credits to prevent overload.
    # min_term_credits is NOT enforced as a hard constraint because prereq
    # chains can force courses into specific terms, making strict minimums
    # infeasible. Light terms are acceptable for feasibility checking.
    for t_idx, term in enumerate(terms):
        term_credits = []
        for course_id, term_vars in X.items():
            if t_idx in term_vars:
                credits = courses[course_id].credits
                term_credits.append(credits * term_vars[t_idx])
        if term_credits:
            total = sum(term_credits)
            model.Add(total <= student.max_term_credits)

    # Constraint 5: Degree requirements.
    for req in requirements:
        # Filter to schedulable courses.
        eligible_vars = []
        eligible_credits = []
        for course_id in req.eligible_courses:
            if course_id in completed:
                # Count toward requirement but don't add constraint.
                eligible_vars.append(model.NewConstant(1))
                eligible_credits.append(courses[course_id].credits)
            elif course_id in X:
                # Course is taken exactly once, so sum of its vars is 0 or 1.
                taken = model.NewBoolVar(f"taken_{course_id}_for_{req.requirement_id}")
                model.Add(taken == sum(X[course_id].values()))
                eligible_vars.append(taken)
                eligible_credits.append(courses[course_id].credits)

        # At least n_of_m courses must be taken.
        model.Add(sum(eligible_vars) >= req.n_of_m)

        # Total credits from this requirement's courses must meet min_credits.
        weighted_credits = [
            eligible_credits[i] * eligible_vars[i] for i in range(len(eligible_vars))
        ]
        model.Add(sum(weighted_credits) >= req.min_credits)

    # Objective (balanced mode): minimize latest term used + slight penalty for summer.
    if optimization_mode == "balanced":
        # Find the latest term any course is scheduled in.
        term_used = []
        for t_idx in range(len(terms)):
            used = model.NewBoolVar(f"term_used_{t_idx}")
            term_vars_in_t = [
                X[c][t_idx] for c in X if t_idx in X[c]
            ]
            if term_vars_in_t:
                model.Add(sum(term_vars_in_t) >= 1).OnlyEnforceIf(used)
                model.Add(sum(term_vars_in_t) == 0).OnlyEnforceIf(used.Not())
            else:
                model.Add(used == 0)
            term_used.append(used)

        # Graduation term is the latest term with a course.
        grad_idx = model.NewIntVar(0, len(terms) - 1, "grad_idx")
        for t_idx in range(len(terms)):
            model.Add(grad_idx >= t_idx).OnlyEnforceIf(term_used[t_idx])

        model.Minimize(grad_idx)

    # Solve.
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout_seconds
    solver.parameters.num_search_workers = 1  # Determinism for reproducibility.

    status_code = solver.Solve(model)
    wall_time = solver.WallTime()

    # Map OR-Tools status to our enum.
    status_map = {
        cp_model.OPTIMAL: SolveStatus.OPTIMAL,
        cp_model.FEASIBLE: SolveStatus.FEASIBLE,
        cp_model.INFEASIBLE: SolveStatus.INFEASIBLE,
        cp_model.MODEL_INVALID: SolveStatus.ERROR,
        cp_model.UNKNOWN: SolveStatus.TIMEOUT_NO_SOLUTION,
    }
    status = status_map.get(status_code, SolveStatus.ERROR)

    # Check for timeout with partial solution.
    if status_code == cp_model.UNKNOWN and solver.ObjectiveValue() is not None:
        try:
            # Try to extract a solution anyway.
            _ = solver.ObjectiveValue()
            status = SolveStatus.TIMEOUT_BEST_EFFORT
        except Exception:
            pass

    # Extract schedule if feasible.
    schedule: dict[str, str] = {}
    grad_term: str | None = None
    if status in (SolveStatus.OPTIMAL, SolveStatus.FEASIBLE, SolveStatus.TIMEOUT_BEST_EFFORT):
        latest_idx = 0
        for course_id, term_vars in X.items():
            for t_idx, var in term_vars.items():
                if solver.Value(var) == 1:
                    schedule[course_id] = terms[t_idx]
                    latest_idx = max(latest_idx, t_idx)
                    break
        grad_term = terms[latest_idx] if terms else None

    return SolveResult(
        status=status,
        schedule=schedule,
        graduation_term=grad_term,
        solver_wall_time=wall_time,
        message=_status_message(status, len(schedule), grad_term),
    )


def _status_message(status: SolveStatus, course_count: int, grad_term: str | None) -> str:
    if status == SolveStatus.OPTIMAL:
        return f"Optimal plan found: {course_count} courses, graduating {grad_term}"
    if status == SolveStatus.FEASIBLE:
        return f"Feasible plan found: {course_count} courses, graduating {grad_term}"
    if status == SolveStatus.INFEASIBLE:
        return "No feasible plan exists within the planning horizon"
    if status == SolveStatus.TIMEOUT_BEST_EFFORT:
        return f"Timeout with best-effort plan: {course_count} courses"
    if status == SolveStatus.TIMEOUT_NO_SOLUTION:
        return "Timeout with no solution found"
    return "Solver error"


def validate_schedule(
    catalog: Catalog,
    student_id: str,
    schedule: dict[str, str],
) -> list[str]:
    """Validate a proposed schedule against all constraints.

    Returns a list of violation messages. Empty list means valid.
    This is used to verify the solver's output and for user-edited plans.
    """
    violations: list[str] = []
    student = catalog.student(student_id)
    courses = catalog.course_map()
    graph = build_graph(catalog)
    completed = set(student.completed_courses)

    from ripplepath.models import term_index, season_of

    # Check each scheduled course.
    for course_id, term in schedule.items():
        if course_id not in courses:
            violations.append(f"{course_id}: unknown course")
            continue
        course = courses[course_id]

        # Check offering.
        if not course.offered_in(term):
            violations.append(
                f"{course_id}: not offered in {season_of(term)} "
                f"(only {course.offered_terms})"
            )

        # Check prerequisites.
        for prereq_id in graph.predecessors(course_id):
            if prereq_id in completed:
                continue
            if prereq_id not in schedule:
                violations.append(f"{course_id}: prerequisite {prereq_id} not scheduled")
            elif term_index(schedule[prereq_id]) >= term_index(term):
                violations.append(
                    f"{course_id}: prerequisite {prereq_id} scheduled in "
                    f"{schedule[prereq_id]} but {course_id} in {term}"
                )

    # Check credit limits per term.
    terms_used: dict[str, list[str]] = {}
    for course_id, term in schedule.items():
        terms_used.setdefault(term, []).append(course_id)

    for term, term_courses in terms_used.items():
        total_credits = sum(courses[c].credits for c in term_courses if c in courses)
        if total_credits > student.max_term_credits:
            violations.append(
                f"{term}: {total_credits} credits exceeds max {student.max_term_credits}"
            )
        # Note: min_term_credits is NOT validated as a hard constraint.
        # Light terms are acceptable when forced by prereq chains.

    # Check degree requirements.
    all_completed = completed | set(schedule.keys())
    requirements = catalog.requirements_for(student.program)
    for req in requirements:
        fulfilled = [c for c in req.eligible_courses if c in all_completed]
        if len(fulfilled) < req.n_of_m:
            violations.append(
                f"{req.requirement_id}: need {req.n_of_m} of "
                f"{len(req.eligible_courses)} courses, have {len(fulfilled)}"
            )
        total_credits = sum(courses[c].credits for c in fulfilled if c in courses)
        if total_credits < req.min_credits:
            violations.append(
                f"{req.requirement_id}: need {req.min_credits} credits, have {total_credits}"
            )

    return violations

# ---------------------------------------------------------------------------
# Phase 4: Minimum Repair Solver
# ---------------------------------------------------------------------------


@dataclass
class RepairResult:
    """Result of a repair attempt after a disruption."""

    status: SolveStatus
    original_schedule: dict[str, str]
    repaired_schedule: dict[str, str]
    disruption_kind: str
    disrupted_course: str
    graduation_delay: int = 0
    """Number of terms the graduation date slipped."""
    courses_moved: int = 0
    """Number of courses assigned to a different term."""
    summer_terms_added: int = 0
    """Number of summer terms that now have courses."""
    solver_wall_time: float = 0.0
    message: str = ""
    affected_courses: list[str] = field(default_factory=list)
    """Courses in the blast radius that needed rescheduling."""

    @property
    def is_feasible(self) -> bool:
        return self.status in (
            SolveStatus.OPTIMAL,
            SolveStatus.FEASIBLE,
            SolveStatus.TIMEOUT_BEST_EFFORT,
        )


def repair_plan(
    catalog: Catalog,
    student_id: str,
    original_schedule: dict[str, str],
    disruption: Disruption,
    timeout_seconds: float = 3.0,
) -> RepairResult:
    """Repair a plan after a disruption with minimum changes.

    The repair objective is lexicographic:
    1. Minimize graduation delay (terms beyond original graduation)
    2. Minimize courses moved (courses assigned to a different term)
    3. Minimize summer terms added (summer terms that now have courses)

    Only courses in the disruption's blast radius are candidates for moving.
    Courses outside the affected cone remain fixed at their original terms.

    Args:
        catalog: The complete data layer snapshot.
        student_id: Student whose plan needs repair.
        original_schedule: The pre-disruption schedule (course_id -> term).
        disruption: The disruption event to repair from.
        timeout_seconds: Max wall-clock time for the solver.

    Returns:
        RepairResult with status, repaired schedule, and repair cost metrics.
    """
    from ripplepath.models import term_index, season_of, STANDARD_SEASONS, term_sequence

    try:
        student = catalog.student(student_id)
    except KeyError as e:
        return RepairResult(
            status=SolveStatus.ERROR,
            original_schedule=original_schedule,
            repaired_schedule={},
            disruption_kind=disruption.kind,
            disrupted_course=disruption.course_id,
            message=str(e),
        )

    graph = build_graph(catalog)
    courses = catalog.course_map()
    completed = set(student.completed_courses)

    # Compute blast radius: everything downstream of the disrupted course.
    try:
        from ripplepath.graph import blast_radius
        affected = blast_radius(graph, disruption.course_id)
        affected.add(disruption.course_id)  # Include the disrupted course itself.
    except KeyError:
        affected = {disruption.course_id}

    # Filter to courses actually in the schedule.
    affected_in_schedule = affected & set(original_schedule.keys())

    # For FAILED_COURSE, the student must retake the course.
    # Mark it as no longer completed if it was.
    if disruption.kind == "FAILED_COURSE" and disruption.course_id in completed:
        completed = completed - {disruption.course_id}

    # Extend planning horizon slightly beyond original graduation in case delay is needed.
    # Allow up to 4 extra terms for repair.
    terms = terms_between(student.current_term, student.target_graduation_term)
    extra_terms = 4
    if terms:
        last_term = terms[-1]
        extended = term_sequence(last_term, extra_terms + 1)[1:]  # Skip current last
        terms = terms + extended
    terms = terms[:20]  # Hard cap for tractability.

    # Determine original graduation position as an INDEX into terms[].
    # Critical: must use the list position, not the global term_index value,
    # because the CP-SAT grad_idx variable is bounded [0, len(terms)-1].
    if original_schedule and terms:
        orig_grad_term = max(
            (t for t in original_schedule.values() if t in terms),
            key=lambda t: terms.index(t),
            default=terms[-1],
        )
    else:
        orig_grad_term = student.target_graduation_term
    orig_grad_idx = terms.index(orig_grad_term) if orig_grad_term in terms else len(terms) - 1

    # Count summer terms that were used in original schedule (before disruption).
    orig_summer_terms = {
        t for t in set(original_schedule.values())
        if season_of(t) not in STANDARD_SEASONS
    }

    # Build the repair model.
    model = cp_model.CpModel()

    # Decision variables: X[c][t] = 1 iff course c is taken in term t.
    X: dict[str, dict[int, cp_model.IntVar]] = {}

    # Courses to schedule: affected courses + any not yet scheduled.
    courses_to_reschedule = affected_in_schedule
    fixed_courses = set(original_schedule.keys()) - affected_in_schedule

    # For affected courses, create variables.
    for course_id in courses_to_reschedule:
        if course_id in completed:
            continue
        if course_id not in courses:
            continue
        course = courses[course_id]
        X[course_id] = {}

        for t_idx, term in enumerate(terms):
            # Skip if disruption blocks this course-term.
            if disruption.blocks_course_in_term(course_id, term):
                continue
            if not course.offered_in(term):
                continue
            X[course_id][t_idx] = model.NewBoolVar(f"X_{course_id}_{t_idx}")

    # Each affected course taken at most once.
    for course_id, term_vars in X.items():
        if term_vars:
            model.AddAtMostOne(term_vars.values())

    # Prerequisites: affected courses must come after their prereqs.
    for course_id in X:
        for prereq_id in graph.predecessors(course_id):
            if prereq_id in completed:
                continue

            # Prereq is fixed (not in blast radius)?
            if prereq_id in fixed_courses:
                prereq_term = original_schedule[prereq_id]
                prereq_idx = terms.index(prereq_term) if prereq_term in terms else -1
                if prereq_idx == -1:
                    continue  # Prereq is outside our horizon, assume completed.
                for t_dep, var_dep in X[course_id].items():
                    if t_dep <= prereq_idx:
                        model.Add(var_dep == 0)
                continue

            # Prereq is also being rescheduled.
            if prereq_id not in X:
                continue

            for t_dep, var_dep in X[course_id].items():
                prereq_before = []
                for t_pre in X[prereq_id]:
                    if t_pre < t_dep:
                        prereq_before.append(X[prereq_id][t_pre])
                if prereq_before:
                    model.Add(sum(prereq_before) >= 1).OnlyEnforceIf(var_dep)
                else:
                    model.Add(var_dep == 0)

    # Credit limits per term (including fixed courses).
    for t_idx, term in enumerate(terms):
        term_credits = []

        # Fixed courses in this term.
        for course_id in fixed_courses:
            if original_schedule.get(course_id) == term:
                term_credits.append(courses[course_id].credits)

        # Variable courses.
        for course_id, term_vars in X.items():
            if t_idx in term_vars:
                credits = courses[course_id].credits
                term_credits.append(credits * term_vars[t_idx])

        if term_credits:
            total = sum(term_credits)
            model.Add(total <= student.max_term_credits)

    # Degree requirements: ensure we still meet all of them.
    requirements = catalog.requirements_for(student.program)
    for req in requirements:
        eligible_vars = []
        eligible_credits = []
        for cid in req.eligible_courses:
            if cid in completed:
                eligible_vars.append(model.NewConstant(1))
                eligible_credits.append(courses[cid].credits)
            elif cid in fixed_courses:
                eligible_vars.append(model.NewConstant(1))
                eligible_credits.append(courses[cid].credits)
            elif cid in X:
                taken = model.NewBoolVar(f"taken_{cid}_for_{req.requirement_id}")
                model.Add(taken == sum(X[cid].values()))
                eligible_vars.append(taken)
                eligible_credits.append(courses[cid].credits)

        model.Add(sum(eligible_vars) >= req.n_of_m)
        weighted_credits = [
            eligible_credits[i] * eligible_vars[i] for i in range(len(eligible_vars))
        ]
        model.Add(sum(weighted_credits) >= req.min_credits)

    # --- Lexicographic Objective ---

    # 1. Graduation delay: the latest term used minus original graduation.
    term_used = []
    for t_idx in range(len(terms)):
        used = model.NewBoolVar(f"term_used_{t_idx}")
        vars_in_t = [X[c][t_idx] for c in X if t_idx in X[c]]
        # Include fixed courses.
        fixed_in_t = any(
            original_schedule.get(c) == terms[t_idx] for c in fixed_courses
        )
        if fixed_in_t:
            model.Add(used == 1)
        elif vars_in_t:
            model.Add(sum(vars_in_t) >= 1).OnlyEnforceIf(used)
            model.Add(sum(vars_in_t) == 0).OnlyEnforceIf(used.Not())
        else:
            model.Add(used == 0)
        term_used.append(used)

    grad_idx = model.NewIntVar(0, len(terms) - 1, "grad_idx")
    for t_idx in range(len(terms)):
        model.Add(grad_idx >= t_idx).OnlyEnforceIf(term_used[t_idx])

    # Graduation delay relative to original.
    delay = model.NewIntVar(-len(terms), len(terms), "delay")
    model.Add(delay == grad_idx - orig_grad_idx)

    # 2. Courses moved: count how many affected courses change term.
    moved_vars = []
    for course_id in X:
        orig_term = original_schedule.get(course_id)
        if orig_term is None:
            continue
        if orig_term not in terms:
            continue
        orig_idx = terms.index(orig_term)

        moved = model.NewBoolVar(f"moved_{course_id}")
        # moved = 1 iff course is NOT in its original term.
        if orig_idx in X[course_id]:
            # not moved = assigned to orig_idx
            model.Add(moved == 1 - X[course_id][orig_idx])
        else:
            # Can't stay in original term (blocked by disruption).
            model.Add(moved == 1)
        moved_vars.append(moved)

    courses_moved = model.NewIntVar(0, len(moved_vars), "courses_moved")
    if moved_vars:
        model.Add(courses_moved == sum(moved_vars))
    else:
        model.Add(courses_moved == 0)

    # 3. Summer terms added: count summer terms with courses that weren't used before.
    summer_added_vars = []
    for t_idx, term in enumerate(terms):
        if season_of(term) in STANDARD_SEASONS:
            continue
        if term in orig_summer_terms:
            continue  # Already used before, doesn't count.
        vars_in_t = [X[c][t_idx] for c in X if t_idx in X[c]]
        if not vars_in_t:
            continue
        summer_used = model.NewBoolVar(f"summer_added_{term}")
        model.Add(sum(vars_in_t) >= 1).OnlyEnforceIf(summer_used)
        model.Add(sum(vars_in_t) == 0).OnlyEnforceIf(summer_used.Not())
        summer_added_vars.append(summer_used)

    summer_added = model.NewIntVar(0, len(summer_added_vars) + 1, "summer_added")
    if summer_added_vars:
        model.Add(summer_added == sum(summer_added_vars))
    else:
        model.Add(summer_added == 0)

    # Lexicographic objective: weighted sum with large coefficients.
    # delay is most important, then courses_moved, then summer_added.
    W_DELAY = 100000
    W_MOVED = 1000
    W_SUMMER = 10
    model.Minimize(W_DELAY * delay + W_MOVED * courses_moved + W_SUMMER * summer_added)

    # Solve.
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout_seconds
    solver.parameters.num_search_workers = 1

    status_code = solver.Solve(model)
    wall_time = solver.WallTime()

    status_map = {
        cp_model.OPTIMAL: SolveStatus.OPTIMAL,
        cp_model.FEASIBLE: SolveStatus.FEASIBLE,
        cp_model.INFEASIBLE: SolveStatus.INFEASIBLE,
        cp_model.MODEL_INVALID: SolveStatus.ERROR,
        cp_model.UNKNOWN: SolveStatus.TIMEOUT_NO_SOLUTION,
    }
    status = status_map.get(status_code, SolveStatus.ERROR)

    if status_code == cp_model.UNKNOWN:
        try:
            _ = solver.ObjectiveValue()
            status = SolveStatus.TIMEOUT_BEST_EFFORT
        except Exception:
            pass

    # Extract repaired schedule.
    repaired: dict[str, str] = {}
    if status in (SolveStatus.OPTIMAL, SolveStatus.FEASIBLE, SolveStatus.TIMEOUT_BEST_EFFORT):
        # Start with fixed courses.
        for course_id in fixed_courses:
            repaired[course_id] = original_schedule[course_id]

        # Add rescheduled courses.
        for course_id, term_vars in X.items():
            for t_idx, var in term_vars.items():
                if solver.Value(var) == 1:
                    repaired[course_id] = terms[t_idx]
                    break

        # Compute metrics.
        grad_delay = solver.Value(delay)
        n_moved = solver.Value(courses_moved)
        n_summer = solver.Value(summer_added)

        # Find which courses actually changed.
        changed = [
            c for c in affected_in_schedule
            if repaired.get(c) != original_schedule.get(c)
        ]

        return RepairResult(
            status=status,
            original_schedule=original_schedule,
            repaired_schedule=repaired,
            disruption_kind=disruption.kind,
            disrupted_course=disruption.course_id,
            graduation_delay=max(0, grad_delay),
            courses_moved=n_moved,
            summer_terms_added=n_summer,
            solver_wall_time=wall_time,
            message=f"Repair found: {n_moved} courses moved, {grad_delay} term delay",
            affected_courses=sorted(changed),
        )

    return RepairResult(
        status=status,
        original_schedule=original_schedule,
        repaired_schedule={},
        disruption_kind=disruption.kind,
        disrupted_course=disruption.course_id,
        solver_wall_time=wall_time,
        message="No repair possible within planning horizon",
        affected_courses=sorted(affected_in_schedule),
    )