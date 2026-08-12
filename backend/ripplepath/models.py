"""Domain models for the Ripple data layer.

These mirror the Supabase tables one-for-one so the offline fixture and the
database are interchangeable. Anything the solver needs to know about the world
is expressed here; the solver itself never reads raw JSON or SQL rows.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Seasons in academic order within a year. Ripple models a quarter system
# because that is what the seeded catalog (Oregon State University) uses.
SEASONS: tuple[str, ...] = ("FA", "WI", "SP", "SU")

# Terms outside FA/WI/SP are "extra" terms the lexicographic repair objective
# tries to avoid adding (priority 3: minimize summer/overload terms added).
STANDARD_SEASONS: frozenset[str] = frozenset({"FA", "WI", "SP"})

Season = Literal["FA", "WI", "SP", "SU"]
Relation = Literal["AND", "OR"]

DisruptionKind = Literal[
    "COURSE_FULL",
    "NOT_OFFERED",
    "FAILED_COURSE",
    "TIME_CONFLICT",
]


class Disruption(BaseModel):
    """A disruption event that invalidates part of a student's plan.

    Used by Phase 4's minimum repair engine. A disruption specifies what went
    wrong; the solver computes how to adapt the plan with minimal changes.
    """

    kind: DisruptionKind
    course_id: str
    term: str | None = None
    """Term where the disruption occurs. None for FAILED_COURSE (affects all future)."""
    description: str = ""
    """Human-readable explanation for UI display."""

    def blocks_course_in_term(self, cid: str, t: str) -> bool:
        """True if this disruption blocks ``cid`` from being taken in ``t``."""
        if self.kind == "FAILED_COURSE":
            # Failed course blocks all future terms for dependents (handled elsewhere).
            # The failed course itself must be retaken.
            return cid == self.course_id
        # For other disruption types, only block the specific course-term pair.
        return cid == self.course_id and t == self.term


def parse_term(term: str) -> tuple[int, str]:
    """Split a term code such as ``2026FA`` into ``(2026, "FA")``."""
    if len(term) != 6:
        raise ValueError(f"term must look like 2026FA, got {term!r}")
    year_part, season = term[:4], term[4:]
    if season not in SEASONS:
        raise ValueError(f"unknown season {season!r} in term {term!r}")
    return int(year_part), season


def term_index(term: str) -> int:
    """Map a term code to a strictly increasing integer.

    The solver needs a total order on terms so "prerequisite strictly before
    dependent" becomes a simple integer inequality.
    """
    year, season = parse_term(term)
    return year * len(SEASONS) + SEASONS.index(season)


def season_of(term: str) -> str:
    return parse_term(term)[1]


def term_sequence(start_term: str, count: int) -> list[str]:
    """Return ``count`` consecutive term codes beginning at ``start_term``."""
    if count < 0:
        raise ValueError("count must be non-negative")
    year, season = parse_term(start_term)
    idx = SEASONS.index(season)
    out: list[str] = []
    for _ in range(count):
        out.append(f"{year}{SEASONS[idx]}")
        idx += 1
        if idx == len(SEASONS):
            idx = 0
            year += 1
    return out


def terms_between(start_term: str, end_term: str) -> list[str]:
    """Inclusive list of terms from ``start_term`` through ``end_term``."""
    span = term_index(end_term) - term_index(start_term) + 1
    if span <= 0:
        return []
    return term_sequence(start_term, span)


class Course(BaseModel):
    """A single catalog course. Mirrors the ``courses`` table."""

    course_id: str
    title: str
    credits: int = Field(ge=0, le=16)
    offered_terms: list[str]
    typical_capacity: int = Field(ge=0)

    @field_validator("offered_terms")
    @classmethod
    def _validate_seasons(cls, value: list[str]) -> list[str]:
        unknown = [s for s in value if s not in SEASONS]
        if unknown:
            raise ValueError(f"unknown seasons {unknown}")
        if not value:
            raise ValueError("a course must be offered in at least one season")
        # Canonical ordering keeps fixture output byte-stable across rebuilds.
        return [s for s in SEASONS if s in value]

    def offered_in(self, term: str) -> bool:
        return season_of(term) in self.offered_terms


class Prerequisite(BaseModel):
    """One prerequisite edge. Mirrors the ``prerequisites`` table.

    Prerequisites are stored as rows rather than an array column because real
    requirements are OR-groups ("MTH 231 or CS 225") and an array cannot
    express that. Semantics:

    * Rows sharing a ``group_id`` form one requirement group.
    * Within a group, members are satisfied by **any** one course (OR).
    * Groups for the same course are **all** required (AND).

    That makes every prerequisite expression a conjunction of disjunctions,
    which is exactly what CP-SAT encodes cleanly in Phase 2.
    """

    course_id: str
    requires_course_id: str
    relation: Relation
    group_id: str


class DegreeRequirement(BaseModel):
    """One graduation rule. Mirrors the ``degree_requirements`` table."""

    program: str
    requirement_id: str
    label: str
    min_credits: int = Field(ge=0)
    n_of_m: int = Field(ge=1)
    eligible_courses: list[str]

    @field_validator("eligible_courses")
    @classmethod
    def _non_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("a requirement needs at least one eligible course")
        return value


class RegistrationState(BaseModel):
    """Seat availability for one course in one term.

    Mirrors the ``registration_state`` table. Seat scarcity is what makes the
    Ripple Score meaningful: the Monte-Carlo model weights a course's
    disruption probability by inverse seat availability.
    """

    course_id: str
    term: str
    available_seats: int = Field(ge=0)
    total_seats: int = Field(ge=0)

    @property
    def fill_ratio(self) -> float:
        """1.0 means completely full, 0.0 means completely empty."""
        if self.total_seats <= 0:
            return 1.0
        taken = self.total_seats - self.available_seats
        return max(0.0, min(1.0, taken / self.total_seats))


class StudentState(BaseModel):
    """A synthetic student. Mirrors the ``student_state`` table.

    Ripple supports both synthetic demo personas and real student scenarios
    provided by the user in local/private deployments.
    """

    student_id: str
    display_name: str
    synthetic: bool = True
    scenario: str
    program: str
    completed_courses: list[str]
    current_term: str
    target_graduation_term: str
    max_term_credits: int = Field(ge=1)
    min_term_credits: int = Field(ge=0)

    @field_validator("target_graduation_term")
    @classmethod
    def _valid_term(cls, value: str) -> str:
        parse_term(value)
        return value

    def planning_terms(self, horizon_cap: int = 12) -> list[str]:
        """Terms the solver may schedule into, capped for tractability.

        The cap matters: an unbounded horizon makes the CP-SAT model blow up,
        and no realistic plan needs more than 12 terms.
        """
        terms = terms_between(self.current_term, self.target_graduation_term)
        return terms[:horizon_cap]


class Program(BaseModel):
    """Degree program metadata."""

    program: str
    institution: str
    label: str
    catalog_year: str
    total_min_credits: int = Field(ge=0)
    source_url: str
    accessed: str


class Catalog(BaseModel):
    """The complete data layer snapshot.

    This is the single object both the Supabase repository and the offline
    fixture repository return, which is what makes the parity test meaningful:
    identical ``Catalog`` in, identical graph out.
    """

    programs: list[Program]
    courses: list[Course]
    prerequisites: list[Prerequisite]
    degree_requirements: list[DegreeRequirement]
    registration_state: list[RegistrationState]
    student_states: list[StudentState]

    def course_map(self) -> dict[str, Course]:
        return {c.course_id: c for c in self.courses}

    def student(self, student_id: str) -> StudentState:
        for s in self.student_states:
            if s.student_id == student_id:
                return s
        raise KeyError(f"unknown student {student_id!r}")

    def requirements_for(self, program: str) -> list[DegreeRequirement]:
        return [r for r in self.degree_requirements if r.program == program]

    def seats(self, course_id: str, term: str) -> RegistrationState | None:
        for row in self.registration_state:
            if row.course_id == course_id and row.term == term:
                return row
        return None

    def prereq_groups(self, course_id: str) -> list[list[str]]:
        """Prerequisites for a course as a list of OR-groups (ANDed together)."""
        groups: dict[str, list[str]] = {}
        for row in self.prerequisites:
            if row.course_id == course_id:
                groups.setdefault(row.group_id, []).append(row.requires_course_id)
        return [groups[k] for k in sorted(groups)]
