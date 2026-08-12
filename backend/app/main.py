import json
import re
import time
from csv import DictReader
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
from io import StringIO
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from fastapi import File, Form, HTTPException, UploadFile

from app.settings import Settings, get_settings
from ripplepath.models import Catalog, StudentState
from ripplepath.repository import load_catalog
from ripplepath.graph import build_graph
from ripplepath.solver import solve_plan, repair_plan, SolveStatus, RepairResult
from ripplepath.score import compute_ripple_score

STARTED_AT = time.time()
settings: Settings = get_settings()


def _upsert_student(student: StudentState) -> None:
    """Insert or replace a student record in the in-memory catalog."""
    global _CATALOG
    for index, existing in enumerate(_CATALOG.student_states):
        if existing.student_id == student.student_id:
            _CATALOG.student_states[index] = student
            return
    _CATALOG.student_states.append(student)


def _validate_student_against_catalog(student: StudentState) -> None:
    courses = set(_CATALOG.course_map().keys())
    missing = sorted(set(student.completed_courses) - courses)
    if missing:
        raise ValueError(f"unknown completed courses: {missing}")

    programs = {p.program for p in _CATALOG.programs}
    if student.program not in programs:
        raise ValueError(
            f"unknown program '{student.program}'. Known programs: {sorted(programs)}"
        )


def _inject_real_student_from_file(path: str) -> None:
    """Load a student JSON file and inject it as non-synthetic."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    student = StudentState.model_validate(payload).model_copy(update={"synthetic": False})
    _validate_student_against_catalog(student)
    _upsert_student(student)


_COURSE_PATTERN = re.compile(r"\b([A-Za-z]{2,6})\s*[- ]?\s*(\d{3}[A-Za-z]?)\b")


def _normalize_course_id(raw: str) -> str:
    match = _COURSE_PATTERN.search(raw)
    if not match:
        return ""
    return f"{match.group(1).upper()} {match.group(2).upper()}"


def _extract_courses_from_text(content: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    skip_line_markers = (
        "student id",
        "student_id",
        "name:",
        "display_name",
        "program:",
        "major:",
        "current term",
        "target graduation term",
    )
    for line in content.splitlines():
        lower = line.lower()
        if any(marker in lower for marker in skip_line_markers):
            continue
        for match in _COURSE_PATTERN.finditer(line):
            cid = f"{match.group(1).upper()} {match.group(2).upper()}"
            if cid not in seen:
                seen.add(cid)
                out.append(cid)
    return out


def _extract_metadata_from_text(content: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in content.splitlines():
        lower = line.lower()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if not value:
            continue
        if key in {"student id", "student_id", "id"}:
            metadata["student_id"] = value
        elif key in {"name", "student", "display_name"}:
            metadata["display_name"] = value
        elif key in {"program", "major"}:
            metadata["program"] = value
        elif key in {"current term", "current_term"}:
            metadata["current_term"] = value.replace(" ", "")
        elif key in {"target graduation term", "target_graduation_term"}:
            metadata["target_graduation_term"] = value.replace(" ", "")
    return metadata


def _parse_student_from_json(content: str) -> StudentState:
    payload = json.loads(content)
    if isinstance(payload, dict) and "student" in payload:
        payload = payload["student"]
    if isinstance(payload, dict) and "courses" in payload and "completed_courses" not in payload:
        payload = dict(payload)
        payload["completed_courses"] = payload.get("courses", [])
    student = StudentState.model_validate(payload).model_copy(update={"synthetic": False})
    return student


def _parse_student_from_csv_or_text(
    content: str,
    *,
    student_id: str,
    display_name: str,
    program: str,
    current_term: str,
    target_graduation_term: str,
    max_term_credits: int,
    min_term_credits: int,
) -> StudentState:
    metadata = _extract_metadata_from_text(content)

    # Try CSV column-based extraction first.
    csv_courses: list[str] = []
    try:
        reader = DictReader(StringIO(content))
        if reader.fieldnames:
            for row in reader:
                for key in ("course_id", "completed_course", "course", "class"):
                    value = (row.get(key) or row.get(key.upper()) or "").strip()
                    normalized = _normalize_course_id(value)
                    if normalized:
                        csv_courses.append(normalized)
    except Exception:
        csv_courses = []

    extracted = csv_courses or _extract_courses_from_text(content)
    extracted = sorted(set(extracted))

    if not extracted:
        raise ValueError(
            "No course IDs detected in transcript. Upload JSON with completed_courses "
            "or CSV/TXT containing values like 'CS 161'."
        )

    courses = extracted

    fallback_program = _CATALOG.programs[0].program if _CATALOG.programs else ""
    student = StudentState(
        student_id=(metadata.get("student_id") or student_id or "real-student").strip(),
        display_name=(metadata.get("display_name") or display_name or "Real Student").strip(),
        synthetic=False,
        scenario="Imported from transcript upload",
        program=(metadata.get("program") or program or fallback_program).strip(),
        completed_courses=courses,
        current_term=(metadata.get("current_term") or current_term or "2026FA").strip(),
        target_graduation_term=(
            metadata.get("target_graduation_term") or target_graduation_term or "2029SP"
        ).strip(),
        max_term_credits=max_term_credits,
        min_term_credits=min_term_credits,
    )
    return student


def _extract_text_from_pdf(raw: bytes) -> str:
    """Extract UTF-8 text from a PDF transcript file."""
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - exercised via runtime env
        raise ValueError(
            "PDF parsing dependency missing. Install pypdf to upload PDF transcripts."
        ) from exc

    try:
        reader = PdfReader(BytesIO(raw))
        text_parts = [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:
        raise ValueError("Could not read PDF transcript. Try exporting a text-based PDF.") from exc

    text = "\n".join(part.strip() for part in text_parts if part and part.strip())
    if not text:
        raise ValueError(
            "No text could be extracted from PDF transcript. "
            "If this is a scanned image PDF, run OCR first."
        )
    return text


def _student_progress(student: StudentState) -> tuple[int, int, list[str]]:
    """Return completed count, remaining count, and remaining course ids."""
    from ripplepath.graph import degree_relevant_courses

    completed = set(student.completed_courses)
    relevant = degree_relevant_courses(_CATALOG, _GRAPH, student.program)
    remaining_ids = sorted(relevant - completed)
    return len(completed), len(remaining_ids), remaining_ids


def _scrub_courses_for_catalog(
    student: StudentState,
) -> tuple[StudentState, list[str], list[str], list[str], list[str]]:
    """Split transcript courses into catalog-recognized and unknown IDs."""
    extracted = sorted(set(student.completed_courses))
    known_ids = set(_CATALOG.course_map().keys())
    recognized = sorted(c for c in extracted if c in known_ids)
    unrecognized = sorted(c for c in extracted if c not in known_ids)

    warnings: list[str] = []
    if unrecognized:
        warnings.append(
            "Some transcript courses do not exist in the active catalog and were "
            "excluded from planning."
        )
    if not recognized:
        warnings.append(
            "No extracted courses matched the active catalog. Student imported "
            "with zero completed courses for planning."
        )

    sanitized = student.model_copy(update={"completed_courses": recognized})
    return sanitized, extracted, recognized, unrecognized, warnings


def _load_runtime_catalog() -> tuple[Catalog, str]:
    catalog, source = load_catalog(
        offline=settings.offline,
        supabase_url=settings.supabase_url,
        supabase_service_key=settings.supabase_service_key,
        fixture_path=settings.fixture_path,
    )
    return catalog, source


# Load catalog once at startup for /health stats.
_CATALOG, _CATALOG_SOURCE = _load_runtime_catalog()
if settings.real_student_file:
    _inject_real_student_from_file(settings.real_student_file)
    _CATALOG_SOURCE = f"{_CATALOG_SOURCE}+real-student"
_GRAPH = build_graph(_CATALOG)

app = FastAPI(
    title="Ripple API",
    description=(
        "Resilience-based academic routing engine. The CP-SAT solver is the "
        "sole source of truth for plan feasibility."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _pkg_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "missing"


class SolverCaps(BaseModel):
    plan: float
    repair: float
    scenario: float


class CatalogStats(BaseModel):
    source: str
    program: str
    catalog_year: str
    courses: int
    prerequisite_edges: int
    degree_requirements: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str = "ripple-api"
    version: str
    environment: str
    git_sha: str
    uptime_seconds: float
    offline_mode: bool
    supabase_configured: bool
    solver_ready: bool
    solver_caps_seconds: SolverCaps
    catalog: CatalogStats
    dependencies: dict[str, str]


def _solver_ready() -> bool:
    """Confirm CP-SAT can actually construct and solve a trivial model.

    This is a real smoke test, not an import check: OR-Tools ships native
    binaries that can import fine yet fail at solve time on a bad platform
    or size-limited serverless host. Catching that in /health means a broken
    deployment is visible immediately instead of during a demo.
    """
    try:
        from ortools.sat.python import cp_model

        model = cp_model.CpModel()
        x = model.NewBoolVar("x")
        y = model.NewBoolVar("y")
        model.AddBoolOr([x, y])
        model.Add(x + y == 1)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 1.0
        result = solver.Solve(model)
        return result in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    except Exception:
        return False


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    solver_ok = _solver_ready()
    return HealthResponse(
        status="ok" if solver_ok else "degraded",
        version=app.version,
        environment=settings.environment,
        git_sha=settings.git_sha,
        uptime_seconds=round(time.time() - STARTED_AT, 3),
        offline_mode=settings.offline,
        supabase_configured=settings.supabase_configured,
        solver_ready=solver_ok,
        solver_caps_seconds=SolverCaps(
            plan=settings.solver_plan_timeout,
            repair=settings.solver_repair_timeout,
            scenario=settings.solver_scenario_timeout,
        ),
        catalog=CatalogStats(
            source=_CATALOG_SOURCE,
            program=_CATALOG.programs[0].program,
            catalog_year=_CATALOG.programs[0].catalog_year,
            courses=len(_CATALOG.courses),
            prerequisite_edges=_GRAPH.number_of_edges(),
            degree_requirements=len(_CATALOG.degree_requirements),
        ),
        dependencies={
            "fastapi": _pkg_version("fastapi"),
            "ortools": _pkg_version("ortools"),
            "networkx": _pkg_version("networkx"),
            "pydantic": _pkg_version("pydantic"),
        },
    )


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {
        "service": "ripple-api",
        "docs": "/docs",
        "health": "/health",
    }


# ---------------------------------------------------------------------------
# Plan API models
# ---------------------------------------------------------------------------


class StudentSummary(BaseModel):
    """Brief student info for the selector."""

    student_id: str
    display_name: str
    scenario: str
    program: str
    current_term: str
    target_graduation_term: str
    completed_credits: int
    remaining_courses: int


class RealStudentImportRequest(BaseModel):
    """Payload for importing a real student scenario at runtime."""

    student_id: str
    display_name: str
    scenario: str = "Real student scenario"
    program: str
    completed_courses: list[str]
    current_term: str
    target_graduation_term: str
    max_term_credits: int = 16
    min_term_credits: int = 12


class RealStudentImportResponse(BaseModel):
    student_id: str
    display_name: str
    synthetic: bool
    total_students: int


class TranscriptImportResponse(BaseModel):
    student_id: str
    display_name: str
    synthetic: bool
    imported_courses: int
    remaining_courses: int
    extracted_course_ids: list[str]
    recognized_course_ids: list[str]
    unrecognized_course_ids: list[str]
    completed_course_ids: list[str]
    remaining_course_ids: list[str]
    warnings: list[str]
    total_students: int


class ScheduledCourse(BaseModel):
    """A course placed in a specific term."""

    course_id: str
    title: str
    credits: int
    term: str


class TermPlan(BaseModel):
    """All courses scheduled for one term."""

    term: str
    courses: list[ScheduledCourse]
    total_credits: int


class PlanResponse(BaseModel):
    """Full degree plan response."""

    student_id: str
    display_name: str
    status: str
    message: str
    graduation_term: str | None
    solver_wall_time: float
    completed_courses: list[ScheduledCourse]
    planned_terms: list[TermPlan]
    total_planned_credits: int


# ---------------------------------------------------------------------------
# Plan API endpoints
# ---------------------------------------------------------------------------


@app.get("/students", response_model=list[StudentSummary], tags=["plan"])
def list_students() -> list[StudentSummary]:
    """List all student scenarios available for planning."""
    courses = _CATALOG.course_map()
    result = []
    for s in _CATALOG.student_states:
        completed_credits = sum(
            courses[c].credits for c in s.completed_courses if c in courses
        )
        # Count remaining degree-relevant courses
        from ripplepath.graph import degree_relevant_courses
        relevant = degree_relevant_courses(_CATALOG, _GRAPH, s.program)
        remaining = len(relevant - set(s.completed_courses))
        result.append(
            StudentSummary(
                student_id=s.student_id,
                display_name=s.display_name,
                scenario=s.scenario,
                program=s.program,
                current_term=s.current_term,
                target_graduation_term=s.target_graduation_term,
                completed_credits=completed_credits,
                remaining_courses=remaining,
            )
        )
    return result


@app.post(
    "/students/import",
    response_model=RealStudentImportResponse,
    tags=["plan"],
)
def import_real_student(request: RealStudentImportRequest) -> RealStudentImportResponse:
    """Import or replace a real student scenario for planning.

    This endpoint mutates only in-memory API state for the running process.
    It does not write to disk or Supabase.
    """
    student = StudentState(
        student_id=request.student_id,
        display_name=request.display_name,
        synthetic=False,
        scenario=request.scenario,
        program=request.program,
        completed_courses=request.completed_courses,
        current_term=request.current_term,
        target_graduation_term=request.target_graduation_term,
        max_term_credits=request.max_term_credits,
        min_term_credits=request.min_term_credits,
    )

    try:
        _validate_student_against_catalog(student)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    _upsert_student(student)
    return RealStudentImportResponse(
        student_id=student.student_id,
        display_name=student.display_name,
        synthetic=student.synthetic,
        total_students=len(_CATALOG.student_states),
    )


@app.post(
    "/students/import-transcript",
    response_model=TranscriptImportResponse,
    tags=["plan"],
)
async def import_transcript(
    file: UploadFile = File(...),
    student_id: str = Form("real-student"),
    display_name: str = Form("Real Student"),
    program: str = Form(""),
    current_term: str = Form("2026FA"),
    target_graduation_term: str = Form("2029SP"),
    max_term_credits: int = Form(16),
    min_term_credits: int = Form(12),
) -> TranscriptImportResponse:
    """Import a student from transcript upload (JSON, CSV, TXT, or PDF).

    Accepted formats:
    - JSON with full StudentState shape or with completed_courses/courses
    - CSV with columns such as course_id/completed_course/course/class
    - Plain text containing course IDs like "CS 161" and optional metadata lines
      (e.g., "Name: ...", "Student ID: ...", "Program: ...")
    - PDF transcript (text-based; scanned PDFs require OCR before upload)
    """
    name = (file.filename or "").lower()
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Uploaded transcript is empty")

    try:
        if name.endswith(".json"):
            content = raw.decode("utf-8", errors="ignore")
            student = _parse_student_from_json(content)
        elif name.endswith(".pdf"):
            content = _extract_text_from_pdf(raw)
            student = _parse_student_from_csv_or_text(
                content,
                student_id=student_id,
                display_name=display_name,
                program=program,
                current_term=current_term,
                target_graduation_term=target_graduation_term,
                max_term_credits=max_term_credits,
                min_term_credits=min_term_credits,
            )
        else:
            content = raw.decode("utf-8", errors="ignore")
            student = _parse_student_from_csv_or_text(
                content,
                student_id=student_id,
                display_name=display_name,
                program=program,
                current_term=current_term,
                target_graduation_term=target_graduation_term,
                max_term_credits=max_term_credits,
                min_term_credits=min_term_credits,
            )

        sanitized, extracted, recognized, unrecognized, warnings = _scrub_courses_for_catalog(
            student
        )
        _validate_student_against_catalog(sanitized)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    _upsert_student(sanitized)
    completed_count, remaining_count, remaining_ids = _student_progress(sanitized)
    return TranscriptImportResponse(
        student_id=sanitized.student_id,
        display_name=sanitized.display_name,
        synthetic=sanitized.synthetic,
        imported_courses=completed_count,
        remaining_courses=remaining_count,
        extracted_course_ids=extracted,
        recognized_course_ids=recognized,
        unrecognized_course_ids=unrecognized,
        completed_course_ids=sorted(set(sanitized.completed_courses)),
        remaining_course_ids=remaining_ids,
        warnings=warnings,
        total_students=len(_CATALOG.student_states),
    )


@app.get("/plan/{student_id}", response_model=PlanResponse, tags=["plan"])
def get_plan(student_id: str) -> PlanResponse:
    """Generate a degree plan for a student using the CP-SAT solver."""
    # Validate student exists.
    try:
        student = _CATALOG.student(student_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Student '{student_id}' not found")

    # Solve the plan.
    result = solve_plan(
        catalog=_CATALOG,
        student_id=student_id,
        timeout_seconds=settings.solver_plan_timeout,
        optimization_mode="balanced",
    )

    courses = _CATALOG.course_map()

    # Build completed courses list.
    completed = [
        ScheduledCourse(
            course_id=c,
            title=courses[c].title if c in courses else c,
            credits=courses[c].credits if c in courses else 0,
            term="completed",
        )
        for c in student.completed_courses
    ]

    # Build planned terms from schedule.
    term_courses: dict[str, list[ScheduledCourse]] = {}
    for course_id, term in result.schedule.items():
        sc = ScheduledCourse(
            course_id=course_id,
            title=courses[course_id].title if course_id in courses else course_id,
            credits=courses[course_id].credits if course_id in courses else 0,
            term=term,
        )
        term_courses.setdefault(term, []).append(sc)

    # Sort terms chronologically and courses alphabetically within each term.
    from ripplepath.models import term_index
    planned_terms = [
        TermPlan(
            term=t,
            courses=sorted(term_courses[t], key=lambda c: c.course_id),
            total_credits=sum(c.credits for c in term_courses[t]),
        )
        for t in sorted(term_courses.keys(), key=term_index)
    ]

    total_planned_credits = sum(tp.total_credits for tp in planned_terms)

    return PlanResponse(
        student_id=student_id,
        display_name=student.display_name,
        status=result.status.value,
        message=result.message,
        graduation_term=result.graduation_term,
        solver_wall_time=round(result.solver_wall_time, 3),
        completed_courses=completed,
        planned_terms=planned_terms,
        total_planned_credits=total_planned_credits,
    )

# ---------------------------------------------------------------------------
# Repair API models (Phase 4)
# ---------------------------------------------------------------------------


class DisruptionRequest(BaseModel):
    """A disruption event that invalidates part of the plan."""

    kind: str  # COURSE_FULL, NOT_OFFERED, FAILED_COURSE, TIME_CONFLICT
    course_id: str
    term: str | None = None
    description: str = ""


class RepairRequest(BaseModel):
    """Request to repair a plan after a disruption."""

    student_id: str
    schedule: dict[str, str]  # course_id -> term
    disruption: DisruptionRequest


class RepairResponse(BaseModel):
    """Result of a repair attempt."""

    status: str
    original_schedule: dict[str, str]
    repaired_schedule: dict[str, str]
    disruption_kind: str
    disrupted_course: str
    graduation_delay: int
    courses_moved: int
    summer_terms_added: int
    solver_wall_time: float
    message: str
    affected_courses: list[str]
    original_terms: list[TermPlan]
    repaired_terms: list[TermPlan]


# ---------------------------------------------------------------------------
# Repair API endpoints
# ---------------------------------------------------------------------------


def _schedule_to_terms(schedule: dict[str, str], courses: dict) -> list[TermPlan]:
    """Convert a schedule dict to a list of TermPlan objects."""
    from ripplepath.models import term_index

    term_courses: dict[str, list[ScheduledCourse]] = {}
    for course_id, term in schedule.items():
        sc = ScheduledCourse(
            course_id=course_id,
            title=courses[course_id].title if course_id in courses else course_id,
            credits=courses[course_id].credits if course_id in courses else 0,
            term=term,
        )
        term_courses.setdefault(term, []).append(sc)

    return [
        TermPlan(
            term=t,
            courses=sorted(term_courses[t], key=lambda c: c.course_id),
            total_credits=sum(c.credits for c in term_courses[t]),
        )
        for t in sorted(term_courses.keys(), key=term_index)
    ]


@app.post("/repair", response_model=RepairResponse, tags=["repair"])
def repair(request: RepairRequest) -> RepairResponse:
    """Repair a plan after a disruption with minimum changes.

    The repair objective is lexicographic:
    1. Minimize graduation delay
    2. Minimize courses moved
    3. Minimize summer terms added

    Only courses in the disruption's blast radius are candidates for moving.
    """
    from ripplepath.models import Disruption, DisruptionKind

    # Validate student exists.
    try:
        student = _CATALOG.student(request.student_id)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Student '{request.student_id}' not found"
        )

    # Convert request to domain model.
    disruption = Disruption(
        kind=request.disruption.kind,  # type: ignore
        course_id=request.disruption.course_id,
        term=request.disruption.term,
        description=request.disruption.description,
    )

    # Run the repair solver.
    result = repair_plan(
        catalog=_CATALOG,
        student_id=request.student_id,
        original_schedule=request.schedule,
        disruption=disruption,
        timeout_seconds=settings.solver_repair_timeout,
    )

    courses = _CATALOG.course_map()

    return RepairResponse(
        status=result.status.value,
        original_schedule=result.original_schedule,
        repaired_schedule=result.repaired_schedule,
        disruption_kind=result.disruption_kind,
        disrupted_course=result.disrupted_course,
        graduation_delay=result.graduation_delay,
        courses_moved=result.courses_moved,
        summer_terms_added=result.summer_terms_added,
        solver_wall_time=round(result.solver_wall_time, 3),
        message=result.message,
        affected_courses=result.affected_courses,
        original_terms=_schedule_to_terms(result.original_schedule, courses),
        repaired_terms=_schedule_to_terms(result.repaired_schedule, courses),
    )


# ---------------------------------------------------------------------------
# Score API models (Phase 5)
# ---------------------------------------------------------------------------


class CourseFragilityResponse(BaseModel):
    course_id: str
    title: str
    disruption_count: int
    delay_count: int
    delay_rate: float
    blast_size: int


class ScenarioResultResponse(BaseModel):
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


class RippleScoreResponse(BaseModel):
    student_id: str
    score: int
    scenario_count: int
    on_time_count: int
    infeasible_count: int
    delay_probability: float
    mean_courses_moved: float
    mean_graduation_delay: float
    course_fragility: list[CourseFragilityResponse]
    scenarios: list[ScenarioResultResponse]
    rng_seed: int
    total_wall_time: float


# ---------------------------------------------------------------------------
# Score API endpoint
# ---------------------------------------------------------------------------


@app.get("/score/{student_id}", response_model=RippleScoreResponse, tags=["score"])
def get_score(student_id: str) -> RippleScoreResponse:
    """Compute the Ripple Score for a student via Monte-Carlo stress test.

    Runs ``n_scenarios`` seeded disruption simulations against the student's
    optimal plan and returns:
    - Ripple Score (0–100): % of scenarios where graduation date is preserved
    - P(delay ≥ 1 term)
    - Mean courses moved per repair
    - Per-course fragility ranking
    """
    # Validate student exists.
    try:
        _CATALOG.student(student_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Student '{student_id}' not found")

    # Solve the base plan first.
    base = solve_plan(
        catalog=_CATALOG,
        student_id=student_id,
        timeout_seconds=settings.solver_plan_timeout,
        optimization_mode="balanced",
    )

    if not base.is_feasible or not base.schedule:
        raise HTTPException(
            status_code=422,
            detail="Cannot compute Ripple Score: no feasible base plan exists",
        )

    # Run the Monte-Carlo stress test.
    result = compute_ripple_score(
        catalog=_CATALOG,
        student_id=student_id,
        base_schedule=base.schedule,
        n_scenarios=settings.stress_scenarios,
        seed=settings.stress_seed,
        scenario_timeout=settings.solver_scenario_timeout,
    )

    return RippleScoreResponse(
        student_id=result.student_id,
        score=result.score,
        scenario_count=result.scenario_count,
        on_time_count=result.on_time_count,
        infeasible_count=result.infeasible_count,
        delay_probability=result.delay_probability,
        mean_courses_moved=result.mean_courses_moved,
        mean_graduation_delay=result.mean_graduation_delay,
        course_fragility=[
            CourseFragilityResponse(
                course_id=c.course_id,
                title=c.title,
                disruption_count=c.disruption_count,
                delay_count=c.delay_count,
                delay_rate=c.delay_rate,
                blast_size=c.blast_size,
            )
            for c in result.course_fragility
        ],
        scenarios=[
            ScenarioResultResponse(
                scenario_index=s.scenario_index,
                disruption_kind=s.disruption_kind,
                disrupted_course=s.disrupted_course,
                disruption_term=s.disruption_term,
                repair_status=s.repair_status,
                graduation_delay=s.graduation_delay,
                courses_moved=s.courses_moved,
                summer_terms_added=s.summer_terms_added,
                affected_course_count=s.affected_course_count,
                solver_wall_time=round(s.solver_wall_time, 4),
            )
            for s in result.scenarios
        ],
        rng_seed=result.rng_seed,
        total_wall_time=result.total_wall_time,
    )


# ---------------------------------------------------------------------------
# Blast radius endpoint (Phase 6)
# ---------------------------------------------------------------------------


class BlastRadiusResponse(BaseModel):
    """Downstream impact of disrupting a single course."""

    student_id: str
    course_id: str
    course_title: str
    blast_radius: list[str]
    """All courses downstream in the catalog graph."""
    in_schedule: list[str]
    """Subset of blast_radius that appear in the student's planned schedule."""
    blast_size: int
    impact_count: int


@app.get(
    "/blast/{student_id}/{course_id:path}",
    response_model=BlastRadiusResponse,
    tags=["simulator"],
)
def get_blast_radius(student_id: str, course_id: str) -> BlastRadiusResponse:
    """Return the blast radius for a course in a student's plan.

    This is a read-only graph query — no solver is involved.
    Used by the Disruption Simulator to highlight affected courses before
    the user commits to running the repair.
    """
    from ripplepath.graph import blast_radius as compute_blast

    # Validate student.
    try:
        student = _CATALOG.student(student_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Student '{student_id}' not found")

    # Validate course.
    courses = _CATALOG.course_map()
    if course_id not in courses:
        raise HTTPException(status_code=404, detail=f"Course '{course_id}' not found")

    # Compute blast radius.
    try:
        radius = compute_blast(_GRAPH, course_id)
    except KeyError:
        radius = set()

    # Solve plan to get the schedule (or use completed + target).
    plan = solve_plan(
        catalog=_CATALOG,
        student_id=student_id,
        timeout_seconds=settings.solver_plan_timeout,
        optimization_mode="balanced",
    )
    scheduled = set(plan.schedule.keys()) if plan.is_feasible else set()

    in_schedule = sorted(radius & scheduled)

    return BlastRadiusResponse(
        student_id=student_id,
        course_id=course_id,
        course_title=courses[course_id].title,
        blast_radius=sorted(radius),
        in_schedule=in_schedule,
        blast_size=len(radius),
        impact_count=len(in_schedule),
    )
