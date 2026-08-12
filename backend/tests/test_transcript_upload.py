"""Tests for transcript upload import endpoint."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_import_transcript_txt_extracts_courses_and_creates_student() -> None:
    transcript = """Name: Jordan Example
Student ID: uwgb-123
Program: OSU-CS-BS
Current Term: 2026FA
Target Graduation Term: 2029SP

Completed Courses:
CS 161
CS 162
MTH 111Z
MTH 112Z
"""

    response = client.post(
        "/students/import-transcript",
        files={"file": ("transcript.txt", transcript, "text/plain")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["student_id"] == "uwgb-123"
    assert body["synthetic"] is False
    assert body["imported_courses"] >= 4
    assert body["remaining_courses"] > 0
    assert len(body["extracted_course_ids"]) >= 4
    assert len(body["recognized_course_ids"]) >= 4
    assert body["unrecognized_course_ids"] == []
    assert "CS 161" in body["completed_course_ids"]
    assert isinstance(body["remaining_course_ids"], list)
    assert body["warnings"] == []


def test_import_transcript_csv_extracts_course_column() -> None:
    csv_data = "course_id\nCS 161\nCS 162\nMTH 111Z\n"
    response = client.post(
        "/students/import-transcript",
        data={
            "student_id": "csv-student",
            "display_name": "CSV Student",
            "program": "OSU-CS-BS",
            "current_term": "2026FA",
            "target_graduation_term": "2029SP",
        },
        files={"file": ("transcript.csv", csv_data, "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["student_id"] == "csv-student"
    assert body["imported_courses"] == 3


def test_import_transcript_json_supports_full_payload() -> None:
    payload = {
        "student_id": "json-student",
        "display_name": "JSON Student",
        "synthetic": False,
        "scenario": "Uploaded transcript",
        "program": "OSU-CS-BS",
        "completed_courses": ["CS 161", "CS 162", "MTH 111Z"],
        "current_term": "2026FA",
        "target_graduation_term": "2029SP",
        "max_term_credits": 16,
        "min_term_credits": 12,
    }
    import json

    response = client.post(
        "/students/import-transcript",
        files={"file": ("student.json", json.dumps(payload), "application/json")},
    )
    assert response.status_code == 200
    assert response.json()["student_id"] == "json-student"


def test_import_transcript_rejects_unknown_courses() -> None:
    transcript = "Name: Invalid\nZZZ 999\n"
    response = client.post(
        "/students/import-transcript",
        files={"file": ("transcript.txt", transcript, "text/plain")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["extracted_course_ids"] == ["ZZZ 999"]
    assert body["recognized_course_ids"] == []
    assert body["unrecognized_course_ids"] == ["ZZZ 999"]
    assert body["imported_courses"] == 0
    assert any("No extracted courses matched the active catalog" in w for w in body["warnings"])


def test_imported_transcript_student_can_be_planned() -> None:
    response = client.get("/plan/uwgb-123")
    assert response.status_code == 200
    plan = response.json()
    assert plan["student_id"] == "uwgb-123"


def test_import_transcript_pdf_uses_pdf_extractor() -> None:
    fake_text = """Name: PDF Student
Student ID: pdf-001
Program: OSU-CS-BS
CS 161
CS 162
MTH 111Z
"""
    with patch("app.main._extract_text_from_pdf", return_value=fake_text):
        response = client.post(
            "/students/import-transcript",
            files={"file": ("transcript.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["student_id"] == "pdf-001"
    assert body["imported_courses"] == 3
    assert len(body["recognized_course_ids"]) == 3
