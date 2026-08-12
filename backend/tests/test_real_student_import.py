"""Tests for runtime import of real student scenarios."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_import_real_student_returns_200_and_non_synthetic() -> None:
    payload = {
        "student_id": "real-student-test-1",
        "display_name": "Real Student Test",
        "scenario": "Imported from advisor transcript.",
        "program": "OSU-CS-BS",
        "completed_courses": ["MTH 111Z", "MTH 112Z", "CS 161", "CS 162"],
        "current_term": "2026FA",
        "target_graduation_term": "2029SP",
        "max_term_credits": 16,
        "min_term_credits": 12,
    }

    response = client.post("/students/import", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["student_id"] == payload["student_id"]
    assert body["synthetic"] is False


def test_imported_student_appears_in_students_endpoint() -> None:
    response = client.get("/students")
    assert response.status_code == 200
    students = response.json()
    ids = {s["student_id"] for s in students}
    assert "real-student-test-1" in ids


def test_imported_student_has_plan_endpoint() -> None:
    response = client.get("/plan/real-student-test-1")
    assert response.status_code == 200
    plan = response.json()
    assert plan["student_id"] == "real-student-test-1"
    assert plan["status"] in ("FEASIBLE", "OPTIMAL", "INFEASIBLE", "TIMEOUT_BEST_EFFORT")


def test_import_rejects_unknown_courses() -> None:
    payload = {
        "student_id": "real-student-invalid-courses",
        "display_name": "Invalid Course Student",
        "scenario": "Bad import",
        "program": "OSU-CS-BS",
        "completed_courses": ["ZZZ 999"],
        "current_term": "2026FA",
        "target_graduation_term": "2029SP",
        "max_term_credits": 16,
        "min_term_credits": 12,
    }

    response = client.post("/students/import", json=payload)
    assert response.status_code == 422
    assert "unknown completed courses" in response.json()["detail"]


def test_import_rejects_unknown_program() -> None:
    payload = {
        "student_id": "real-student-invalid-program",
        "display_name": "Invalid Program Student",
        "scenario": "Bad import",
        "program": "UWGB-CS-BS",
        "completed_courses": ["MTH 111Z"],
        "current_term": "2026FA",
        "target_graduation_term": "2029SP",
        "max_term_credits": 16,
        "min_term_credits": 12,
    }

    response = client.post("/students/import", json=payload)
    assert response.status_code == 422
    assert "unknown program" in response.json()["detail"]
