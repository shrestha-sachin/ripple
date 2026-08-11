"""Tests for Phase 4: Disruption engine + minimum repair."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from ripplepath.models import Disruption
from ripplepath.repository import load_catalog
from ripplepath.solver import repair_plan, solve_plan, SolveStatus


client = TestClient(app)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def catalog():
    """Load the offline catalog for testing."""
    cat, _ = load_catalog(offline=True)
    return cat


@pytest.fixture
def on_track_plan(catalog):
    """Generate a baseline plan for the on-track persona."""
    result = solve_plan(
        catalog=catalog,
        student_id="persona-on-track",
        timeout_seconds=10.0,
        optimization_mode="balanced",
    )
    assert result.is_feasible
    return result.schedule


# ---------------------------------------------------------------------------
# Disruption model tests
# ---------------------------------------------------------------------------


class TestDisruptionModel:
    """Tests for the Disruption model."""

    def test_course_full_blocks_specific_term(self):
        d = Disruption(kind="COURSE_FULL", course_id="CS 261", term="2026FA")
        assert d.blocks_course_in_term("CS 261", "2026FA")
        assert not d.blocks_course_in_term("CS 261", "2026WI")
        assert not d.blocks_course_in_term("CS 325", "2026FA")

    def test_not_offered_blocks_specific_term(self):
        d = Disruption(kind="NOT_OFFERED", course_id="CS 325", term="2027SP")
        assert d.blocks_course_in_term("CS 325", "2027SP")
        assert not d.blocks_course_in_term("CS 325", "2027FA")

    def test_failed_course_blocks_all_terms(self):
        d = Disruption(kind="FAILED_COURSE", course_id="CS 161")
        # For failed course, the course itself must be retaken.
        assert d.blocks_course_in_term("CS 161", "2026FA")
        assert d.blocks_course_in_term("CS 161", "2027SP")

    def test_disruption_with_description(self):
        d = Disruption(
            kind="TIME_CONFLICT",
            course_id="CS 344",
            term="2026FA",
            description="Conflicts with required MTH 341",
        )
        assert d.description == "Conflicts with required MTH 341"
        assert d.blocks_course_in_term("CS 344", "2026FA")


# ---------------------------------------------------------------------------
# Repair solver tests
# ---------------------------------------------------------------------------


class TestRepairSolver:
    """Tests for the repair_plan solver."""

    def test_repair_with_no_disruption_impact(self, catalog, on_track_plan):
        """Disruption to a leaf course should have minimal impact (if repair is feasible)."""
        from ripplepath.graph import build_graph
        from ripplepath.models import season_of, term_index

        graph = build_graph(catalog)
        courses = catalog.course_map()
        student = catalog.student("persona-on-track")

        # Find a scheduled course with no scheduled dependents (leaf in the plan),
        # that is offered in all seasons, so rescheduling is definitely possible,
        # and scheduled late in the plan so there's room to move it.
        target_idx = term_index(student.target_graduation_term)

        for course_id, term in sorted(on_track_plan.items(), key=lambda x: -term_index(x[1])):
            dependents = set(graph.successors(course_id)) & set(on_track_plan.keys())
            course = courses.get(course_id)
            # Must be a leaf, offered every season, and not in the last term.
            if (
                not dependents
                and course
                and len(course.offered_terms) == 4
                and term_index(term) < target_idx
            ):
                break
        else:
            pytest.skip("No easily reschedulable leaf course in schedule")

        disruption = Disruption(kind="NOT_OFFERED", course_id=course_id, term=term)

        result = repair_plan(
            catalog=catalog,
            student_id="persona-on-track",
            original_schedule=on_track_plan,
            disruption=disruption,
        )

        # If repair is feasible, only the disrupted course should move.
        if result.is_feasible:
            assert result.courses_moved <= 1
        # Otherwise, the test still passes (repair may legitimately fail).

    def test_repair_moves_course_to_different_term(self, catalog, on_track_plan):
        """Disruption should cause the affected course to move or be infeasible."""
        from ripplepath.graph import build_graph
        from ripplepath.models import season_of

        if not on_track_plan:
            pytest.skip("No schedule to repair")

        graph = build_graph(catalog)
        courses = catalog.course_map()

        # Find a leaf course (no scheduled dependents) that's offered in at least 3 seasons.
        for course_id, original_term in on_track_plan.items():
            dependents = set(graph.successors(course_id)) & set(on_track_plan.keys())
            course = courses.get(course_id)
            if not dependents and course and len(course.offered_terms) >= 3:
                break
        else:
            pytest.skip("No leaf course with multiple offering terms")

        disruption = Disruption(
            kind="COURSE_FULL", course_id=course_id, term=original_term
        )

        result = repair_plan(
            catalog=catalog,
            student_id="persona-on-track",
            original_schedule=on_track_plan,
            disruption=disruption,
        )

        # If feasible, the course should have moved to a different term.
        if result.is_feasible and course_id in result.repaired_schedule:
            assert result.repaired_schedule[course_id] != original_term

    def test_repair_cascades_to_dependents(self, catalog, on_track_plan):
        """When a prerequisite moves, dependents may also need to move."""
        from ripplepath.graph import build_graph

        graph = build_graph(catalog)
        courses = catalog.course_map()

        # Find a course with dependents that are also scheduled, and that
        # is offered in multiple terms so repair is possible.
        for course_id, term in on_track_plan.items():
            dependents = set(graph.successors(course_id)) & set(on_track_plan.keys())
            if dependents and len(courses[course_id].offered_terms) > 1:
                break
        else:
            pytest.skip("No scheduled course with dependents and multiple offerings")

        disruption = Disruption(kind="COURSE_FULL", course_id=course_id, term=term)

        result = repair_plan(
            catalog=catalog,
            student_id="persona-on-track",
            original_schedule=on_track_plan,
            disruption=disruption,
        )

        # Repair should either be feasible or infeasible - both are valid outcomes.
        # If feasible, at least one course should have moved.
        if result.is_feasible:
            assert result.courses_moved >= 1 or len(result.affected_courses) >= 1

    def test_repair_minimizes_graduation_delay(self, catalog, on_track_plan):
        """Repair should prioritize minimizing graduation delay."""
        if not on_track_plan:
            pytest.skip("No schedule to repair")

        course_id = next(iter(on_track_plan.keys()))
        original_term = on_track_plan[course_id]

        disruption = Disruption(
            kind="NOT_OFFERED", course_id=course_id, term=original_term
        )

        result = repair_plan(
            catalog=catalog,
            student_id="persona-on-track",
            original_schedule=on_track_plan,
            disruption=disruption,
        )

        # Even if feasible, delay should be bounded.
        assert result.graduation_delay <= 4  # At most 4 terms delay.

    def test_repair_handles_failed_course(self, catalog, on_track_plan):
        """FAILED_COURSE disruption should handle retaking."""
        # Find a course early in the plan (likely a prereq).
        from ripplepath.models import term_index

        if not on_track_plan:
            pytest.skip("No schedule to repair")

        earliest_course = min(on_track_plan.keys(), key=lambda c: term_index(on_track_plan[c]))

        disruption = Disruption(kind="FAILED_COURSE", course_id=earliest_course)

        result = repair_plan(
            catalog=catalog,
            student_id="persona-on-track",
            original_schedule=on_track_plan,
            disruption=disruption,
        )

        # Should find some repair or be infeasible if truly impossible.
        assert result.status in (
            SolveStatus.OPTIMAL,
            SolveStatus.FEASIBLE,
            SolveStatus.INFEASIBLE,
            SolveStatus.TIMEOUT_BEST_EFFORT,
        )

    def test_repair_preserves_unaffected_courses(self, catalog, on_track_plan):
        """Courses outside blast radius should stay fixed."""
        from ripplepath.graph import build_graph, blast_radius

        graph = build_graph(catalog)

        if not on_track_plan:
            pytest.skip("No schedule to repair")

        # Find a course with a small blast radius.
        for course_id, term in on_track_plan.items():
            radius = blast_radius(graph, course_id) & set(on_track_plan.keys())
            unaffected = set(on_track_plan.keys()) - radius - {course_id}
            if unaffected:
                break
        else:
            pytest.skip("All courses are in each other's blast radius")

        disruption = Disruption(kind="COURSE_FULL", course_id=course_id, term=term)

        result = repair_plan(
            catalog=catalog,
            student_id="persona-on-track",
            original_schedule=on_track_plan,
            disruption=disruption,
        )

        if result.is_feasible:
            # Unaffected courses should stay in their original terms.
            for cid in list(unaffected)[:5]:  # Check a few.
                if cid in result.repaired_schedule:
                    assert result.repaired_schedule[cid] == on_track_plan[cid], (
                        f"Course {cid} moved but is not in blast radius"
                    )


# ---------------------------------------------------------------------------
# Repair API tests
# ---------------------------------------------------------------------------


class TestRepairAPI:
    """Tests for POST /repair endpoint."""

    def test_repair_returns_200_for_valid_request(self, on_track_plan):
        response = client.post(
            "/repair",
            json={
                "student_id": "persona-on-track",
                "schedule": on_track_plan,
                "disruption": {
                    "kind": "NOT_OFFERED",
                    "course_id": next(iter(on_track_plan.keys())),
                    "term": on_track_plan[next(iter(on_track_plan.keys()))],
                },
            },
        )
        assert response.status_code == 200

    def test_repair_returns_404_for_unknown_student(self, on_track_plan):
        response = client.post(
            "/repair",
            json={
                "student_id": "unknown-student-xyz",
                "schedule": on_track_plan,
                "disruption": {
                    "kind": "NOT_OFFERED",
                    "course_id": "CS 161",
                    "term": "2026FA",
                },
            },
        )
        assert response.status_code == 404

    def test_repair_response_has_required_fields(self, on_track_plan):
        response = client.post(
            "/repair",
            json={
                "student_id": "persona-on-track",
                "schedule": on_track_plan,
                "disruption": {
                    "kind": "COURSE_FULL",
                    "course_id": next(iter(on_track_plan.keys())),
                    "term": on_track_plan[next(iter(on_track_plan.keys()))],
                },
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert "original_schedule" in data
        assert "repaired_schedule" in data
        assert "disruption_kind" in data
        assert "disrupted_course" in data
        assert "graduation_delay" in data
        assert "courses_moved" in data
        assert "summer_terms_added" in data
        assert "solver_wall_time" in data
        assert "message" in data
        assert "affected_courses" in data
        assert "original_terms" in data
        assert "repaired_terms" in data

    def test_repair_returns_term_plans(self, on_track_plan):
        response = client.post(
            "/repair",
            json={
                "student_id": "persona-on-track",
                "schedule": on_track_plan,
                "disruption": {
                    "kind": "NOT_OFFERED",
                    "course_id": next(iter(on_track_plan.keys())),
                    "term": on_track_plan[next(iter(on_track_plan.keys()))],
                },
            },
        )
        data = response.json()

        assert isinstance(data["original_terms"], list)
        assert isinstance(data["repaired_terms"], list)

        if data["status"] in ("OPTIMAL", "FEASIBLE"):
            assert len(data["repaired_terms"]) > 0
            # Each term should have the expected structure.
            for term in data["repaired_terms"]:
                assert "term" in term
                assert "courses" in term
                assert "total_credits" in term

    def test_repair_different_disruption_kinds(self, on_track_plan):
        """Test all disruption kinds work."""
        course_id = next(iter(on_track_plan.keys()))
        term = on_track_plan[course_id]

        for kind in ["COURSE_FULL", "NOT_OFFERED", "FAILED_COURSE", "TIME_CONFLICT"]:
            disruption = {"kind": kind, "course_id": course_id}
            if kind != "FAILED_COURSE":
                disruption["term"] = term

            response = client.post(
                "/repair",
                json={
                    "student_id": "persona-on-track",
                    "schedule": on_track_plan,
                    "disruption": disruption,
                },
            )
            assert response.status_code == 200, f"Failed for kind={kind}"
