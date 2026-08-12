"""Tests for Phase 6: Disruption Simulator — blast radius endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestBlastRadiusEndpoint:
    """Tests for GET /blast/{student_id}/{course_id}."""

    def test_blast_returns_200_for_valid_inputs(self):
        response = client.get("/blast/persona-on-track/CS 261")
        assert response.status_code == 200

    def test_blast_returns_404_for_unknown_student(self):
        response = client.get("/blast/unknown-student/CS 261")
        assert response.status_code == 404

    def test_blast_returns_404_for_unknown_course(self):
        response = client.get("/blast/persona-on-track/ZZZ 999")
        assert response.status_code == 404

    def test_blast_has_required_fields(self):
        response = client.get("/blast/persona-on-track/CS 261")
        data = response.json()

        assert "student_id" in data
        assert "course_id" in data
        assert "course_title" in data
        assert "blast_radius" in data
        assert "in_schedule" in data
        assert "blast_size" in data
        assert "impact_count" in data

    def test_blast_radius_is_list_of_strings(self):
        response = client.get("/blast/persona-on-track/CS 261")
        data = response.json()
        assert isinstance(data["blast_radius"], list)
        assert all(isinstance(c, str) for c in data["blast_radius"])

    def test_in_schedule_is_subset_of_blast_radius(self):
        response = client.get("/blast/persona-on-track/CS 261")
        data = response.json()
        radius_set = set(data["blast_radius"])
        in_schedule_set = set(data["in_schedule"])
        assert in_schedule_set.issubset(radius_set)

    def test_blast_size_matches_radius_length(self):
        response = client.get("/blast/persona-on-track/CS 261")
        data = response.json()
        assert data["blast_size"] == len(data["blast_radius"])

    def test_impact_count_matches_in_schedule_length(self):
        response = client.get("/blast/persona-on-track/CS 261")
        data = response.json()
        assert data["impact_count"] == len(data["in_schedule"])

    def test_cs_261_has_large_blast_radius(self):
        """CS 261 is described as the highest-fanout course in the catalog."""
        response = client.get("/blast/persona-on-track/CS 261")
        data = response.json()
        # Should have meaningful downstream impact.
        assert data["blast_size"] > 5

    def test_leaf_course_has_zero_blast_radius(self):
        """A course with no dependents should have an empty blast radius."""
        from ripplepath.graph import build_graph
        from ripplepath.repository import load_catalog

        cat, _ = load_catalog(offline=True)
        graph = build_graph(cat)

        # Find a course with no successors.
        leaf = next(
            (c for c in graph.nodes if graph.out_degree(c) == 0),
            None,
        )
        if leaf is None:
            pytest.skip("No leaf course in graph")

        response = client.get(f"/blast/persona-on-track/{leaf}")
        # May 404 if this course isn't accessible via the endpoint path encoding.
        if response.status_code == 200:
            data = response.json()
            assert data["blast_size"] == 0
            assert data["impact_count"] == 0

    def test_blast_course_title_is_populated(self):
        response = client.get("/blast/persona-on-track/CS 161")
        data = response.json()
        assert data["course_title"]
        assert data["course_title"] != "CS 161"  # Should be full title

    def test_blast_all_personas(self):
        for student_id in ["persona-on-track", "persona-transfer", "persona-failed-gateway"]:
            response = client.get(f"/blast/{student_id}/CS 161")
            assert response.status_code == 200, f"Failed for {student_id}"
