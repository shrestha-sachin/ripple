"""Tests for /students and /plan/{student_id} API endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestStudentsEndpoint:
    """Tests for GET /students."""

    def test_students_returns_list(self):
        response = client.get("/students")
        assert response.status_code == 200
        students = response.json()
        assert isinstance(students, list)
        assert len(students) == 3  # 3 personas in catalog

    def test_students_have_required_fields(self):
        response = client.get("/students")
        students = response.json()
        for student in students:
            assert "student_id" in student
            assert "display_name" in student
            assert "scenario" in student
            assert "program" in student
            assert "current_term" in student
            assert "target_graduation_term" in student
            assert "completed_credits" in student
            assert "remaining_courses" in student

    def test_students_include_known_personas(self):
        response = client.get("/students")
        students = response.json()
        ids = [s["student_id"] for s in students]
        assert "persona-on-track" in ids
        assert "persona-transfer" in ids
        assert "persona-failed-gateway" in ids


class TestPlanEndpoint:
    """Tests for GET /plan/{student_id}."""

    def test_plan_returns_200_for_valid_student(self):
        response = client.get("/plan/persona-on-track")
        assert response.status_code == 200

    def test_plan_returns_404_for_unknown_student(self):
        response = client.get("/plan/unknown-student-xyz")
        assert response.status_code == 404

    def test_plan_has_required_fields(self):
        response = client.get("/plan/persona-on-track")
        plan = response.json()
        assert "student_id" in plan
        assert "display_name" in plan
        assert "status" in plan
        assert "message" in plan
        assert "graduation_term" in plan
        assert "solver_wall_time" in plan
        assert "completed_courses" in plan
        assert "planned_terms" in plan
        assert "total_planned_credits" in plan

    def test_plan_status_is_feasible_or_optimal(self):
        response = client.get("/plan/persona-on-track")
        plan = response.json()
        # CP-SAT should find a valid plan for the on-track persona
        assert plan["status"] in ("FEASIBLE", "OPTIMAL")

    def test_plan_has_graduation_term_when_feasible(self):
        response = client.get("/plan/persona-on-track")
        plan = response.json()
        if plan["status"] in ("FEASIBLE", "OPTIMAL"):
            assert plan["graduation_term"] is not None
            assert len(plan["graduation_term"]) == 6  # e.g. "2027SP"

    def test_plan_includes_completed_courses(self):
        response = client.get("/plan/persona-on-track")
        plan = response.json()
        assert isinstance(plan["completed_courses"], list)
        # On-track persona has completed courses
        assert len(plan["completed_courses"]) > 0

    def test_plan_includes_planned_terms(self):
        response = client.get("/plan/persona-on-track")
        plan = response.json()
        assert isinstance(plan["planned_terms"], list)
        # Should have future terms with courses
        if plan["status"] in ("FEASIBLE", "OPTIMAL"):
            assert len(plan["planned_terms"]) > 0

    def test_planned_term_has_courses(self):
        response = client.get("/plan/persona-on-track")
        plan = response.json()
        if plan["planned_terms"]:
            term = plan["planned_terms"][0]
            assert "term" in term
            assert "courses" in term
            assert "total_credits" in term
            assert isinstance(term["courses"], list)

    def test_transfer_student_plan_is_feasible(self):
        response = client.get("/plan/persona-transfer")
        assert response.status_code == 200
        plan = response.json()
        assert plan["status"] in ("FEASIBLE", "OPTIMAL")

    def test_failed_gateway_student_plan_is_feasible(self):
        response = client.get("/plan/persona-failed-gateway")
        assert response.status_code == 200
        plan = response.json()
        assert plan["status"] in ("FEASIBLE", "OPTIMAL")
