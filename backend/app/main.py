import time
from importlib.metadata import PackageNotFoundError, version
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from fastapi import HTTPException

from app.settings import Settings, get_settings
from ripplepath.repository import load_catalog
from ripplepath.graph import build_graph
from ripplepath.solver import solve_plan, repair_plan, SolveStatus, RepairResult

STARTED_AT = time.time()

# Load catalog once at startup for /health stats.
_CATALOG, _CATALOG_SOURCE = load_catalog(offline=True)
_GRAPH = build_graph(_CATALOG)

app = FastAPI(
    title="Ripple API",
    description=(
        "Resilience-based academic routing engine. The CP-SAT solver is the "
        "sole source of truth for plan feasibility."
    ),
    version="0.1.0",
)

settings: Settings = get_settings()

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
    """List all synthetic student personas available for planning."""
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