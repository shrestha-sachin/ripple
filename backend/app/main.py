import time
from importlib.metadata import PackageNotFoundError, version
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.settings import Settings, get_settings

STARTED_AT = time.time()

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
