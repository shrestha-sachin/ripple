"""Phase 2 oracle tests: CP-SAT feasibility solver.

These are "oracle tests" because they verify known-good and known-bad scenarios
where the correct answer is predetermined. The solver is the sole source of
truth for feasibility, so we test it against hand-crafted cases.
"""

from __future__ import annotations

import pytest

from ripplepath.catalog_source import build_catalog
from ripplepath.graph import build_graph, topological_depth
from ripplepath.models import (
    Catalog,
    Course,
    DegreeRequirement,
    Prerequisite,
    Program,
    RegistrationState,
    StudentState,
    term_index,
    terms_between,
)
from ripplepath.solver import (
    SolveResult,
    SolveStatus,
    check_feasibility,
    solve_plan,
    validate_schedule,
)


# ---------------------------------------------------------------------------
# Test fixtures: minimal catalog for oracle tests
# ---------------------------------------------------------------------------


def _mini_catalog() -> Catalog:
    """A tiny catalog for fast, deterministic solver tests."""
    return Catalog(
        programs=[
            Program(
                program="MINI-CS",
                institution="Test University",
                label="Mini CS",
                catalog_year="2026-2027",
                total_min_credits=16,
                source_url="https://example.com",
                accessed="2026-08-10",
            ),
        ],
        courses=[
            Course(
                course_id="CS 101",
                title="Intro",
                credits=4,
                offered_terms=["FA", "WI", "SP"],
                typical_capacity=100,
            ),
            Course(
                course_id="CS 201",
                title="Intermediate",
                credits=4,
                offered_terms=["FA", "WI", "SP"],
                typical_capacity=50,
            ),
            Course(
                course_id="CS 301",
                title="Advanced",
                credits=4,
                offered_terms=["FA", "SP"],  # Not offered in winter!
                typical_capacity=30,
            ),
            Course(
                course_id="CS 401",
                title="Capstone",
                credits=4,
                offered_terms=["SP"],  # Spring only.
                typical_capacity=25,
            ),
        ],
        prerequisites=[
            Prerequisite(
                course_id="CS 201",
                requires_course_id="CS 101",
                relation="AND",
                group_id="CS201-G1",
            ),
            Prerequisite(
                course_id="CS 301",
                requires_course_id="CS 201",
                relation="AND",
                group_id="CS301-G1",
            ),
            Prerequisite(
                course_id="CS 401",
                requires_course_id="CS 301",
                relation="AND",
                group_id="CS401-G1",
            ),
        ],
        degree_requirements=[
            DegreeRequirement(
                program="MINI-CS",
                requirement_id="CORE",
                label="Core courses",
                min_credits=16,
                n_of_m=4,
                eligible_courses=["CS 101", "CS 201", "CS 301", "CS 401"],
            ),
        ],
        registration_state=[
            RegistrationState(course_id="CS 101", term="2026FA", available_seats=50, total_seats=100),
            RegistrationState(course_id="CS 101", term="2027WI", available_seats=50, total_seats=100),
            RegistrationState(course_id="CS 101", term="2027SP", available_seats=50, total_seats=100),
            RegistrationState(course_id="CS 201", term="2026FA", available_seats=25, total_seats=50),
            RegistrationState(course_id="CS 201", term="2027WI", available_seats=25, total_seats=50),
            RegistrationState(course_id="CS 201", term="2027SP", available_seats=25, total_seats=50),
            RegistrationState(course_id="CS 301", term="2026FA", available_seats=15, total_seats=30),
            RegistrationState(course_id="CS 301", term="2027SP", available_seats=15, total_seats=30),
            RegistrationState(course_id="CS 401", term="2027SP", available_seats=12, total_seats=25),
            RegistrationState(course_id="CS 401", term="2028SP", available_seats=12, total_seats=25),
        ],
        student_states=[
            StudentState(
                student_id="mini-freshman",
                display_name="Mini Freshman",
                synthetic=True,
                scenario="greenfield",
                program="MINI-CS",
                completed_courses=[],
                current_term="2026FA",
                target_graduation_term="2028SP",
                max_term_credits=16,
                min_term_credits=4,
            ),
            StudentState(
                student_id="mini-advanced",
                display_name="Mini Advanced",
                synthetic=True,
                scenario="advanced",
                program="MINI-CS",
                completed_courses=["CS 101", "CS 201"],
                current_term="2027WI",
                target_graduation_term="2028SP",
                max_term_credits=16,
                min_term_credits=4,
            ),
            StudentState(
                student_id="mini-impossible",
                display_name="Mini Impossible",
                synthetic=True,
                scenario="impossible",
                program="MINI-CS",
                completed_courses=[],
                current_term="2027SP",  # Only 2 terms to complete 4-course chain!
                target_graduation_term="2027SU",
                max_term_credits=16,
                min_term_credits=4,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Oracle tests: known feasible scenarios
# ---------------------------------------------------------------------------


class TestFeasibleScenarios:
    """Scenarios where the solver MUST find a valid plan."""

    def test_freshman_can_graduate_with_long_horizon(self):
        """A freshman with 8 terms can complete a 4-course chain."""
        catalog = _mini_catalog()
        result = solve_plan(catalog, "mini-freshman", timeout_seconds=5.0)

        assert result.is_feasible, f"Expected feasible, got {result.status}: {result.message}"
        assert len(result.schedule) == 4, f"Expected 4 courses, got {len(result.schedule)}"
        assert result.graduation_term is not None

    def test_advanced_student_finishes_remaining_courses(self):
        """A student with 2 courses done can finish the remaining 2."""
        catalog = _mini_catalog()
        result = solve_plan(catalog, "mini-advanced", timeout_seconds=5.0)

        assert result.is_feasible
        # Should only schedule CS 301 and CS 401.
        assert len(result.schedule) == 2
        assert "CS 301" in result.schedule
        assert "CS 401" in result.schedule
        # CS 101 and CS 201 should not appear (already completed).
        assert "CS 101" not in result.schedule
        assert "CS 201" not in result.schedule

    def test_solver_respects_prerequisite_ordering(self):
        """Prerequisites must be scheduled strictly before dependents."""
        catalog = _mini_catalog()
        result = solve_plan(catalog, "mini-freshman", timeout_seconds=5.0)

        assert result.is_feasible
        schedule = result.schedule

        # Chain: CS 101 -> CS 201 -> CS 301 -> CS 401
        assert term_index(schedule["CS 101"]) < term_index(schedule["CS 201"])
        assert term_index(schedule["CS 201"]) < term_index(schedule["CS 301"])
        assert term_index(schedule["CS 301"]) < term_index(schedule["CS 401"])

    def test_solver_respects_term_offerings(self):
        """Courses can only be scheduled in terms they are offered."""
        catalog = _mini_catalog()
        result = solve_plan(catalog, "mini-freshman", timeout_seconds=5.0)

        assert result.is_feasible
        courses = catalog.course_map()

        for course_id, term in result.schedule.items():
            course = courses[course_id]
            assert course.offered_in(term), (
                f"{course_id} scheduled in {term} but offered in {course.offered_terms}"
            )

    def test_capstone_must_be_spring(self):
        """CS 401 (spring only) must be scheduled in a spring term."""
        catalog = _mini_catalog()
        result = solve_plan(catalog, "mini-freshman", timeout_seconds=5.0)

        assert result.is_feasible
        capstone_term = result.schedule["CS 401"]
        assert capstone_term.endswith("SP"), f"Capstone in {capstone_term}, expected spring"


# ---------------------------------------------------------------------------
# Oracle tests: known infeasible scenarios
# ---------------------------------------------------------------------------


class TestInfeasibleScenarios:
    """Scenarios where no valid plan exists."""

    def test_impossible_horizon_is_infeasible(self):
        """Cannot complete 4-course chain in 2 terms."""
        catalog = _mini_catalog()
        result = solve_plan(catalog, "mini-impossible", timeout_seconds=5.0)

        assert not result.is_feasible, f"Expected infeasible, got {result.status}"
        assert result.status == SolveStatus.INFEASIBLE

    def test_missing_student_returns_error(self):
        """Unknown student ID returns an error status."""
        catalog = _mini_catalog()
        result = solve_plan(catalog, "nonexistent-student", timeout_seconds=5.0)

        assert result.status == SolveStatus.ERROR
        assert "unknown student" in result.message.lower()


# ---------------------------------------------------------------------------
# Oracle tests: real catalog with synthetic personas
# ---------------------------------------------------------------------------


class TestRealCatalogFeasibility:
    """Test feasibility against the actual OSU CS catalog."""

    @pytest.fixture
    def real_catalog(self) -> Catalog:
        return build_catalog()

    def test_on_track_persona_is_feasible(self, real_catalog: Catalog):
        """The on-track persona should have a feasible plan."""
        result = solve_plan(real_catalog, "persona-on-track", timeout_seconds=10.0)

        assert result.is_feasible, f"On-track infeasible: {result.message}"
        assert len(result.schedule) > 0

    def test_failed_gateway_persona_is_feasible(self, real_catalog: Catalog):
        """The failed-gateway persona should still have a feasible plan."""
        result = solve_plan(real_catalog, "persona-failed-gateway", timeout_seconds=10.0)

        assert result.is_feasible, f"Failed-gateway infeasible: {result.message}"

    def test_transfer_persona_is_feasible(self, real_catalog: Catalog):
        """The transfer student persona should have a feasible plan."""
        result = solve_plan(real_catalog, "persona-transfer", timeout_seconds=10.0)

        assert result.is_feasible, f"Transfer infeasible: {result.message}"

    def test_schedule_passes_validation(self, real_catalog: Catalog):
        """Solver output must pass our own validation function."""
        result = solve_plan(real_catalog, "persona-on-track", timeout_seconds=10.0)

        if result.is_feasible:
            violations = validate_schedule(real_catalog, "persona-on-track", result.schedule)
            assert len(violations) == 0, f"Schedule violations: {violations}"


# ---------------------------------------------------------------------------
# Schedule validation tests
# ---------------------------------------------------------------------------


class TestScheduleValidation:
    """Test the schedule validator catches constraint violations."""

    def test_valid_schedule_has_no_violations(self):
        """A solver-produced schedule should validate cleanly."""
        catalog = _mini_catalog()
        result = solve_plan(catalog, "mini-freshman", timeout_seconds=5.0)
        assert result.is_feasible

        violations = validate_schedule(catalog, "mini-freshman", result.schedule)
        assert len(violations) == 0, f"Unexpected violations: {violations}"

    def test_catches_prerequisite_violation(self):
        """Validator catches out-of-order prerequisites."""
        catalog = _mini_catalog()
        bad_schedule = {
            "CS 101": "2027WI",  # Should be before CS 201.
            "CS 201": "2026FA",  # Before CS 101!
            "CS 301": "2027SP",
            "CS 401": "2028SP",
        }

        violations = validate_schedule(catalog, "mini-freshman", bad_schedule)
        assert any("prerequisite" in v.lower() for v in violations)

    def test_catches_offering_violation(self):
        """Validator catches courses scheduled in wrong season."""
        catalog = _mini_catalog()
        bad_schedule = {
            "CS 101": "2026FA",
            "CS 201": "2027WI",
            "CS 301": "2027WI",  # CS 301 is not offered in winter!
            "CS 401": "2028SP",
        }

        violations = validate_schedule(catalog, "mini-freshman", bad_schedule)
        assert any("not offered" in v.lower() for v in violations)

    def test_catches_credit_limit_violation(self):
        """Validator catches exceeding max credits per term."""
        catalog = _mini_catalog()
        # Create a modified catalog with lower credit limit.
        modified_states = [
            StudentState(
                student_id="mini-freshman",
                display_name="Mini Freshman",
                synthetic=True,
                scenario="greenfield",
                program="MINI-CS",
                completed_courses=[],
                current_term="2026FA",
                target_graduation_term="2028SP",
                max_term_credits=8,  # Reduced!
                min_term_credits=4,
            ),
        ] + [s for s in catalog.student_states if s.student_id != "mini-freshman"]
        modified_catalog = catalog.model_copy(update={"student_states": modified_states})

        # 3 courses in one term = 12 credits, exceeds max of 8.
        bad_schedule_overload = {
            "CS 101": "2026FA",
            "CS 201": "2026FA",
            "CS 301": "2026FA",  # 12 credits in FA!
            "CS 401": "2028SP",
        }

        violations = validate_schedule(modified_catalog, "mini-freshman", bad_schedule_overload)
        assert any("exceeds max" in v.lower() for v in violations)


# ---------------------------------------------------------------------------
# Solver determinism and reproducibility
# ---------------------------------------------------------------------------


class TestSolverProperties:
    """Non-functional properties of the solver."""

    def test_solver_is_deterministic(self):
        """Same input produces same output."""
        catalog = _mini_catalog()
        result1 = solve_plan(catalog, "mini-freshman", timeout_seconds=5.0)
        result2 = solve_plan(catalog, "mini-freshman", timeout_seconds=5.0)

        assert result1.status == result2.status
        assert result1.schedule == result2.schedule

    def test_feasibility_check_is_fast(self):
        """check_feasibility completes quickly on mini catalog."""
        catalog = _mini_catalog()
        result = check_feasibility(catalog, "mini-freshman", timeout_seconds=1.0)

        assert result.is_feasible
        assert result.solver_wall_time < 1.0

    def test_solver_respects_timeout(self):
        """Solver returns within the timeout window."""
        catalog = build_catalog()  # Real, larger catalog.
        result = solve_plan(catalog, "greenfield", timeout_seconds=2.0)

        # Allow some margin for overhead.
        assert result.solver_wall_time < 3.0


# ---------------------------------------------------------------------------
# Integration: graph + solver consistency
# ---------------------------------------------------------------------------


class TestGraphSolverConsistency:
    """Ensure the graph and solver agree on structure."""

    def test_topological_depth_bounds_schedule(self):
        """Course with depth d cannot be scheduled before term d."""
        catalog = _mini_catalog()
        graph = build_graph(catalog)
        depths = topological_depth(graph)
        result = solve_plan(catalog, "mini-freshman", timeout_seconds=5.0)

        assert result.is_feasible
        terms = terms_between(
            catalog.student("mini-freshman").current_term,
            catalog.student("mini-freshman").target_graduation_term,
        )

        for course_id, term in result.schedule.items():
            term_idx = terms.index(term)
            depth = depths[course_id]
            assert term_idx >= depth, (
                f"{course_id} at depth {depth} scheduled in term index {term_idx}"
            )

    def test_real_catalog_chain_depth(self):
        """The real catalog has meaningful prerequisite chains."""
        catalog = build_catalog()
        graph = build_graph(catalog)
        depths = topological_depth(graph)

        # CS 162 (Data Structures) should have depth >= 1 (needs CS 161).
        assert depths.get("CS 162", 0) >= 1

        # Capstone should have significant depth.
        max_depth = max(depths.values())
        assert max_depth >= 3, f"Expected deep chain, max depth is {max_depth}"
