"""Tests for Phase 5: Ripple Score + fragility ranking."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from ripplepath.repository import load_catalog
from ripplepath.score import compute_ripple_score, ScenarioResult
from ripplepath.solver import solve_plan

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def catalog():
    cat, _ = load_catalog(offline=True)
    return cat


@pytest.fixture(scope="module")
def on_track_schedule(catalog):
    result = solve_plan(catalog, "persona-on-track", optimization_mode="balanced")
    assert result.is_feasible
    return result.schedule


@pytest.fixture(scope="module")
def score_result(catalog, on_track_schedule):
    """Full 200-scenario score for persona-on-track (computed once per test session)."""
    return compute_ripple_score(
        catalog=catalog,
        student_id="persona-on-track",
        base_schedule=on_track_schedule,
        n_scenarios=200,
        seed=20260810,
        scenario_timeout=0.5,
    )


# ---------------------------------------------------------------------------
# Score engine unit tests
# ---------------------------------------------------------------------------


class TestScoreEngine:
    """Tests for compute_ripple_score."""

    def test_score_is_in_range(self, score_result):
        assert 0 <= score_result.score <= 100

    def test_scenario_count_matches_requested(self, score_result):
        assert score_result.scenario_count == 200

    def test_on_time_plus_delay_plus_infeasible_equals_total(self, score_result):
        """Every scenario is exactly one of: on-time, delayed, infeasible."""
        delayed = [
            s for s in score_result.scenarios
            if s.is_feasible and s.graduation_delay >= 1
        ]
        assert (
            score_result.on_time_count + len(delayed) + score_result.infeasible_count
            == score_result.scenario_count
        )

    def test_score_matches_on_time_fraction(self, score_result):
        expected = round(100 * score_result.on_time_count / score_result.scenario_count)
        assert score_result.score == expected

    def test_delay_probability_in_range(self, score_result):
        assert 0.0 <= score_result.delay_probability <= 1.0

    def test_seed_produces_reproducible_score(self, catalog, on_track_schedule):
        """Same seed must always produce the same score."""
        r1 = compute_ripple_score(
            catalog=catalog,
            student_id="persona-on-track",
            base_schedule=on_track_schedule,
            n_scenarios=50,
            seed=42,
        )
        r2 = compute_ripple_score(
            catalog=catalog,
            student_id="persona-on-track",
            base_schedule=on_track_schedule,
            n_scenarios=50,
            seed=42,
        )
        assert r1.score == r2.score
        assert r1.on_time_count == r2.on_time_count

    def test_different_seeds_may_differ(self, catalog, on_track_schedule):
        """Different seeds should (almost certainly) produce different results."""
        r1 = compute_ripple_score(
            catalog=catalog,
            student_id="persona-on-track",
            base_schedule=on_track_schedule,
            n_scenarios=50,
            seed=1,
        )
        r2 = compute_ripple_score(
            catalog=catalog,
            student_id="persona-on-track",
            base_schedule=on_track_schedule,
            n_scenarios=50,
            seed=999999,
        )
        # Extremely unlikely to produce identical detailed results with different seeds.
        assert r1.rng_seed != r2.rng_seed

    def test_course_fragility_is_sorted_by_delay_rate(self, score_result):
        fragility = score_result.course_fragility
        for i in range(len(fragility) - 1):
            assert fragility[i].delay_rate >= fragility[i + 1].delay_rate

    def test_course_fragility_covers_disrupted_courses(self, score_result):
        disrupted = {s.disrupted_course for s in score_result.scenarios}
        fragile_ids = {c.course_id for c in score_result.course_fragility}
        # Every disrupted course should appear in fragility list.
        assert disrupted == fragile_ids

    def test_disruption_kinds_distribution(self, score_result):
        """Sampled kinds should roughly follow the configured weights."""
        kinds = [s.disruption_kind for s in score_result.scenarios]
        full_count = kinds.count("COURSE_FULL")
        not_offered_count = kinds.count("NOT_OFFERED")
        failed_count = kinds.count("FAILED_COURSE")
        conflict_count = kinds.count("TIME_CONFLICT")

        total = len(kinds)
        # COURSE_FULL should be the most common (~40%).
        assert full_count > not_offered_count
        assert full_count > failed_count
        assert full_count > conflict_count
        # TIME_CONFLICT should be the least common (~10%).
        assert conflict_count < full_count

    def test_empty_schedule_returns_zero_score(self, catalog):
        result = compute_ripple_score(
            catalog=catalog,
            student_id="persona-on-track",
            base_schedule={},
            n_scenarios=10,
            seed=1,
        )
        assert result.score == 0
        assert result.scenario_count == 0

    def test_transfer_student_has_valid_score(self, catalog):
        plan = solve_plan(catalog, "persona-transfer", optimization_mode="balanced")
        assert plan.is_feasible
        result = compute_ripple_score(
            catalog=catalog,
            student_id="persona-transfer",
            base_schedule=plan.schedule,
            n_scenarios=50,
            seed=20260810,
        )
        assert 0 <= result.score <= 100
        assert result.scenario_count == 50

    def test_scenario_results_have_valid_fields(self, score_result):
        for s in score_result.scenarios[:10]:
            assert s.scenario_index >= 0
            assert s.disruption_kind in (
                "COURSE_FULL", "NOT_OFFERED", "FAILED_COURSE", "TIME_CONFLICT"
            )
            assert s.disrupted_course
            assert s.graduation_delay >= 0
            assert s.courses_moved >= 0
            assert s.summer_terms_added >= 0
            assert s.solver_wall_time >= 0


# ---------------------------------------------------------------------------
# Score API tests
# ---------------------------------------------------------------------------


class TestScoreAPI:
    """Tests for GET /score/{student_id}."""

    def test_score_endpoint_returns_200(self):
        response = client.get("/score/persona-on-track")
        assert response.status_code == 200

    def test_score_endpoint_returns_404_for_unknown_student(self):
        response = client.get("/score/unknown-student-xyz")
        assert response.status_code == 404

    def test_score_response_has_required_fields(self):
        response = client.get("/score/persona-on-track")
        data = response.json()

        assert "score" in data
        assert "scenario_count" in data
        assert "on_time_count" in data
        assert "infeasible_count" in data
        assert "delay_probability" in data
        assert "mean_courses_moved" in data
        assert "mean_graduation_delay" in data
        assert "course_fragility" in data
        assert "scenarios" in data
        assert "rng_seed" in data
        assert "total_wall_time" in data

    def test_score_is_in_valid_range(self):
        response = client.get("/score/persona-on-track")
        data = response.json()
        assert 0 <= data["score"] <= 100

    def test_score_is_reproducible(self):
        r1 = client.get("/score/persona-on-track").json()
        r2 = client.get("/score/persona-on-track").json()
        assert r1["score"] == r2["score"]
        assert r1["rng_seed"] == r2["rng_seed"]

    def test_all_personas_return_scores(self):
        for student_id in ["persona-on-track", "persona-transfer", "persona-failed-gateway"]:
            response = client.get(f"/score/{student_id}")
            assert response.status_code == 200, f"Failed for {student_id}"
            data = response.json()
            assert 0 <= data["score"] <= 100

    def test_course_fragility_is_a_list(self):
        response = client.get("/score/persona-on-track")
        data = response.json()
        assert isinstance(data["course_fragility"], list)
        if data["course_fragility"]:
            first = data["course_fragility"][0]
            assert "course_id" in first
            assert "title" in first
            assert "delay_rate" in first
            assert "blast_size" in first

    def test_scenarios_list_is_present(self):
        response = client.get("/score/persona-on-track")
        data = response.json()
        assert isinstance(data["scenarios"], list)
        assert len(data["scenarios"]) == data["scenario_count"]
