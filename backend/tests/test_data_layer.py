"""Phase 1 verification: data layer, offline/Supabase parity, and DAG integrity.

The mandated Phase 1 checks are:
  * the catalog loads from Supabase AND from the offline fixture, and both
    produce identical prerequisite graphs;
  * the prerequisite graph is a DAG;
  * the seeded curriculum is real (>= 50 courses, genuine prereq chains,
    fall-only/spring-only courses present);
  * three synthetic personas exist and are clearly labelled fictional.
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pytest

from ripplepath.catalog_source import PROGRAM, build_catalog
from ripplepath.export_fixtures import render_seed_sql
from ripplepath.graph import (
    blast_radius,
    build_graph,
    degree_relevant_courses,
    earliest_feasible_index,
    graph_signature,
    topological_depth,
)
from ripplepath.models import (
    Catalog,
    Course,
    STANDARD_SEASONS,
    term_index,
    term_sequence,
    terms_between,
)
from ripplepath.repository import FIXTURE_PATH, FixtureRepository, SupabaseRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def source_catalog() -> Catalog:
    return build_catalog()


@pytest.fixture(scope="module")
def fixture_catalog() -> Catalog:
    return FixtureRepository().load()


# ---------------------------------------------------------------------------
# Source / fixture parity  (the mandated Phase 1 verification)
# ---------------------------------------------------------------------------
def test_fixture_file_exists() -> None:
    assert FIXTURE_PATH.exists(), (
        "seed/fixtures.json is missing. Run: python -m ripplepath.export_fixtures"
    )


def test_fixture_matches_source_exactly(
    source_catalog: Catalog, fixture_catalog: Catalog
) -> None:
    """The committed fixture must be a faithful dump of the source catalog."""
    assert fixture_catalog.model_dump() == source_catalog.model_dump()


def test_fixture_is_deterministic(source_catalog: Catalog) -> None:
    """Re-exporting produces byte-identical JSON, so rebuilds show empty diffs."""
    rebuilt = json.dumps(build_catalog().model_dump(), indent=2, sort_keys=True) + "\n"
    assert rebuilt == FIXTURE_PATH.read_text(encoding="utf-8")


def test_offline_and_supabase_produce_identical_graphs(
    source_catalog: Catalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Supabase and the offline fixture must yield the same prerequisite graph.

    The Supabase read is exercised through its real ``load`` method with the
    HTTP layer stubbed to return the seeded rows, so a schema/field-name drift
    between the two sources would fail this test.
    """
    payload = source_catalog.model_dump()

    class _StubResponse:
        def __init__(self, rows: list[dict]) -> None:
            self._rows = rows

        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict]:
            return self._rows

    class _StubClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> "_StubClient":
            return self

        def __exit__(self, *exc) -> None:
            return None

        def get(self, url: str, params: dict) -> _StubResponse:
            table = url.rstrip("/").rsplit("/", 1)[-1]
            return _StubResponse(payload[table])

    monkeypatch.setattr("ripplepath.repository.httpx.Client", _StubClient)

    supabase_catalog = SupabaseRepository("https://stub.supabase.co", "test-key").load()
    offline_catalog = FixtureRepository().load()

    supabase_graph = build_graph(supabase_catalog)
    offline_graph = build_graph(offline_catalog)

    assert graph_signature(supabase_graph) == graph_signature(offline_graph)
    assert supabase_catalog.model_dump() == offline_catalog.model_dump()


def test_load_catalog_falls_back_when_supabase_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Demo safety: an unreachable Supabase must not raise, it must fall back."""
    from ripplepath import repository

    def _boom(*args, **kwargs):
        raise ConnectionError("simulated network blip")

    monkeypatch.setattr(repository.SupabaseRepository, "load", _boom)

    catalog, source = repository.load_catalog(
        offline=False,
        supabase_url="https://stub.supabase.co",
        supabase_service_key="test-key",
    )
    assert source == "fixture-fallback"
    assert len(catalog.courses) > 0


# ---------------------------------------------------------------------------
# DAG integrity
# ---------------------------------------------------------------------------
def test_prerequisite_graph_is_a_dag(fixture_catalog: Catalog) -> None:
    graph = build_graph(fixture_catalog)
    assert nx.is_directed_acyclic_graph(graph)


def test_graph_rejects_a_cycle(fixture_catalog: Catalog) -> None:
    """A cyclic catalog must fail loudly rather than reach the solver."""
    from ripplepath.graph import PrerequisiteGraphError
    from ripplepath.models import Prerequisite

    broken = fixture_catalog.model_copy(deep=True)
    broken.prerequisites.append(
        Prerequisite(
            course_id="CS 161",
            requires_course_id="CS 461",
            relation="AND",
            group_id="cycle:g0",
        )
    )
    with pytest.raises(PrerequisiteGraphError, match="cycle"):
        build_graph(broken)


def test_graph_rejects_unknown_course_reference(fixture_catalog: Catalog) -> None:
    from ripplepath.graph import PrerequisiteGraphError
    from ripplepath.models import Prerequisite

    broken = fixture_catalog.model_copy(deep=True)
    broken.prerequisites.append(
        Prerequisite(
            course_id="CS 161",
            requires_course_id="CS 999",
            relation="AND",
            group_id="ghost:g0",
        )
    )
    with pytest.raises(PrerequisiteGraphError, match="missing from the catalog"):
        build_graph(broken)


# ---------------------------------------------------------------------------
# Catalog realism  (Phase 1 asks for a real, published curriculum)
# ---------------------------------------------------------------------------
def test_catalog_size_meets_phase_1_target(fixture_catalog: Catalog) -> None:
    """Target is 50-80 courses across one degree program."""
    assert 50 <= len(fixture_catalog.courses) <= 80


def test_course_ids_are_unique(fixture_catalog: Catalog) -> None:
    ids = [c.course_id for c in fixture_catalog.courses]
    assert len(ids) == len(set(ids))


def test_provenance_is_recorded(fixture_catalog: Catalog) -> None:
    """Compliance: every program records its public source URL and access date."""
    assert fixture_catalog.programs
    for program in fixture_catalog.programs:
        assert program.source_url.startswith("https://")
        assert program.accessed
        assert program.institution


def test_genuine_prerequisite_chains_exist(fixture_catalog: Catalog) -> None:
    """Deep chains are what make disruptions ripple; assert they are present."""
    graph = build_graph(fixture_catalog)
    depth = topological_depth(graph)
    assert max(depth.values()) >= 5, f"deepest chain is only {max(depth.values())}"


def test_known_prerequisite_edges_match_the_public_catalog(
    fixture_catalog: Catalog,
) -> None:
    """Spot-check transcription against the OSU catalog prerequisite strings."""
    graph = build_graph(fixture_catalog)
    for prereq, dependent in [
        ("CS 161", "CS 162"),
        ("CS 162", "CS 261"),
        ("CS 261", "CS 325"),
        ("CS 261", "CS 361"),
        ("CS 362", "CS 461"),
        ("CS 461", "CS 462"),
        ("CS 462", "CS 463"),
        ("MTH 251Z", "MTH 252Z"),
        ("CS 381", "CS 480"),
    ]:
        assert graph.has_edge(prereq, dependent), f"missing edge {prereq} -> {dependent}"


def test_or_groups_are_representable(fixture_catalog: Catalog) -> None:
    """CS 261 needs CS 162 AND (CS 225 OR MTH 231) - the canonical OR-group.

    This is the case an array column on `courses` could not express, and is the
    reason `prerequisites` is a separate table.
    """
    groups = fixture_catalog.prereq_groups("CS 261")
    assert len(groups) == 2
    as_sets = [set(g) for g in groups]
    assert {"CS 162"} in as_sets
    assert {"CS 225", "MTH 231"} in as_sets

    or_rows = [
        r
        for r in fixture_catalog.prerequisites
        if r.course_id == "CS 261" and r.relation == "OR"
    ]
    assert {r.requires_course_id for r in or_rows} == {"CS 225", "MTH 231"}


def test_seasonal_scarcity_exists(fixture_catalog: Catalog) -> None:
    """Fall-only and spring-only courses are the source of real fragility."""
    single_season = [c for c in fixture_catalog.courses if len(c.offered_terms) == 1]
    assert len(single_season) >= 8

    by_id = fixture_catalog.course_map()
    assert by_id["CS 321"].offered_terms == ["FA"], "CS 321 should be fall-only"
    assert by_id["CS 461"].offered_terms == ["FA"]
    assert by_id["CS 462"].offered_terms == ["WI"]
    assert by_id["CS 463"].offered_terms == ["SP"]
    # CS 225 is deliberately unavailable in spring.
    assert "SP" not in by_id["CS 225"].offered_terms


def test_degree_requirements_are_satisfiable_in_principle(
    fixture_catalog: Catalog,
) -> None:
    """Each requirement must have enough eligible courses to meet n_of_m.

    This is a data sanity check, not a feasibility ruling - CP-SAT decides
    feasibility in Phase 2.
    """
    known = set(fixture_catalog.course_map())
    for requirement in fixture_catalog.requirements_for(PROGRAM):
        eligible = [c for c in requirement.eligible_courses if c in known]
        assert len(eligible) == len(requirement.eligible_courses), (
            f"{requirement.requirement_id} references unknown courses"
        )
        assert len(eligible) >= requirement.n_of_m, (
            f"{requirement.requirement_id} needs {requirement.n_of_m} of "
            f"{len(eligible)} eligible courses"
        )
        best = sorted(
            (fixture_catalog.course_map()[c].credits for c in eligible), reverse=True
        )[: requirement.n_of_m]
        assert sum(best) >= requirement.min_credits, (
            f"{requirement.requirement_id} can never reach {requirement.min_credits} "
            f"credits from {requirement.n_of_m} courses"
        )


def test_registration_state_covers_every_offered_course_term(
    fixture_catalog: Catalog,
) -> None:
    """A missing row means 'not offered', so offered terms must all have rows."""
    keyed = {(r.course_id, r.term) for r in fixture_catalog.registration_state}
    horizon = term_sequence("2026FA", 12)
    for course in fixture_catalog.courses:
        for term in horizon:
            if course.offered_in(term):
                assert (course.course_id, term) in keyed, (
                    f"no registration row for {course.course_id} in {term}"
                )


def test_registration_state_is_internally_consistent(
    fixture_catalog: Catalog,
) -> None:
    for row in fixture_catalog.registration_state:
        assert 0 <= row.available_seats <= row.total_seats
        assert 0.0 <= row.fill_ratio <= 1.0


def test_bottleneck_courses_are_seat_scarce(fixture_catalog: Catalog) -> None:
    """The Ripple Score weights disruption by inverse availability, so the
    high-fanout courses must actually be scarce in the seeded data."""
    row = fixture_catalog.seats("CS 261", "2026FA")
    assert row is not None
    assert row.fill_ratio > 0.9, "CS 261 should be nearly full to drive fragility"


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------
def test_three_personas_exist_and_are_synthetic(fixture_catalog: Catalog) -> None:
    students = fixture_catalog.student_states
    assert len(students) == 3
    for student in students:
        # Compliance: no real student data, ever.
        assert student.synthetic is True
        assert student.student_id.startswith("persona-")
        assert student.scenario
        assert student.min_term_credits <= student.max_term_credits


def test_personas_cover_the_required_scenarios(fixture_catalog: Catalog) -> None:
    ids = {s.student_id for s in fixture_catalog.student_states}
    assert ids == {
        "persona-on-track",
        "persona-transfer",
        "persona-failed-gateway",
    }


def test_persona_completed_courses_are_real_and_prereq_consistent(
    fixture_catalog: Catalog,
) -> None:
    """A persona's completed set must itself be internally consistent."""
    known = set(fixture_catalog.course_map())
    for student in fixture_catalog.student_states:
        completed = set(student.completed_courses)
        assert completed <= known, (
            f"{student.student_id} claims unknown courses: {sorted(completed - known)}"
        )
        for course_id in completed:
            for group in fixture_catalog.prereq_groups(course_id):
                assert completed & set(group), (
                    f"{student.student_id} completed {course_id} without any of {group}"
                )


def test_failed_gateway_persona_has_not_completed_the_gateway(
    fixture_catalog: Catalog,
) -> None:
    """The scenario only makes sense if CS 261 is genuinely still outstanding."""
    student = fixture_catalog.student("persona-failed-gateway")
    assert "CS 261" not in student.completed_courses


def test_transfer_persona_has_no_cs_credit(fixture_catalog: Catalog) -> None:
    student = fixture_catalog.student("persona-transfer")
    assert not [c for c in student.completed_courses if c.startswith("CS ")]


def test_persona_horizons_are_capped_at_twelve_terms(
    fixture_catalog: Catalog,
) -> None:
    """Solver scale guard: the planning horizon never exceeds 12 terms."""
    for student in fixture_catalog.student_states:
        terms = student.planning_terms()
        assert 0 < len(terms) <= 12
        assert terms[0] == student.current_term


# ---------------------------------------------------------------------------
# Graph analysis used by later phases
# ---------------------------------------------------------------------------
def test_blast_radius_of_the_gateway_course_is_large(
    fixture_catalog: Catalog,
) -> None:
    """CS 261 is the bottleneck; losing it must visibly ripple downstream."""
    graph = build_graph(fixture_catalog)
    downstream = blast_radius(graph, "CS 261")
    assert len(downstream) >= 20
    for expected in ("CS 325", "CS 361", "CS 461", "CS 463"):
        assert expected in downstream


def test_blast_radius_of_a_leaf_is_empty(fixture_catalog: Catalog) -> None:
    graph = build_graph(fixture_catalog)
    assert blast_radius(graph, "CS 463") == set()


def test_blast_radius_rejects_unknown_course(fixture_catalog: Catalog) -> None:
    graph = build_graph(fixture_catalog)
    with pytest.raises(KeyError):
        blast_radius(graph, "CS 999")


def test_degree_relevant_closure_is_smaller_than_the_catalog(
    fixture_catalog: Catalog,
) -> None:
    """Scale guard: the solver models the program closure, not everything."""
    graph = build_graph(fixture_catalog)
    relevant = degree_relevant_courses(fixture_catalog, graph, PROGRAM)
    assert relevant
    assert relevant <= set(graph.nodes)
    # The closure must include prerequisites that are not themselves required.
    assert "CS 162" in relevant


def test_earliest_feasible_index_respects_offerings_and_depth(
    fixture_catalog: Catalog,
) -> None:
    """Courses can never be placed before their season or their chain allows."""
    graph = build_graph(fixture_catalog)
    student = fixture_catalog.student("persona-transfer")
    terms = student.planning_terms()
    completed = set(student.completed_courses)
    earliest = earliest_feasible_index(fixture_catalog, graph, completed, terms)
    courses = fixture_catalog.course_map()

    for course_id, index in earliest.items():
        assert courses[course_id].offered_in(terms[index]), (
            f"{course_id} placed in {terms[index]} but offered "
            f"{courses[course_id].offered_terms}"
        )

    # Bo has no CS credit, so the whole chain must start from CS 161.
    assert earliest["CS 161"] < earliest["CS 162"] < earliest["CS 261"]
    assert earliest["CS 261"] < earliest["CS 461"]


def test_completed_courses_are_excluded_from_earliest_index(
    fixture_catalog: Catalog,
) -> None:
    graph = build_graph(fixture_catalog)
    student = fixture_catalog.student("persona-on-track")
    terms = student.planning_terms()
    earliest = earliest_feasible_index(
        fixture_catalog, graph, set(student.completed_courses), terms
    )
    for done in student.completed_courses:
        assert done not in earliest


# ---------------------------------------------------------------------------
# Term arithmetic
# ---------------------------------------------------------------------------
def test_term_ordering_is_strictly_increasing() -> None:
    terms = term_sequence("2026FA", 8)
    assert terms[:5] == ["2026FA", "2026WI", "2026SP", "2026SU", "2027FA"]
    indices = [term_index(t) for t in terms]
    assert indices == sorted(indices)
    assert len(set(indices)) == len(indices)


def test_terms_between_is_inclusive() -> None:
    assert terms_between("2026FA", "2026SP") == ["2026FA", "2026WI", "2026SP"]
    assert terms_between("2026FA", "2026FA") == ["2026FA"]
    assert terms_between("2027FA", "2026FA") == []


def test_summer_is_not_a_standard_season() -> None:
    """The repair objective penalises added summer terms, so they must be
    distinguishable from the standard academic year."""
    assert "SU" not in STANDARD_SEASONS
    assert STANDARD_SEASONS == {"FA", "WI", "SP"}


def test_invalid_term_codes_are_rejected() -> None:
    from ripplepath.models import parse_term

    for bad in ["2026XX", "26FA", "2026", "2026fa1"]:
        with pytest.raises(ValueError):
            parse_term(bad)


def test_course_rejects_unknown_season() -> None:
    with pytest.raises(ValueError, match="unknown seasons"):
        Course(
            course_id="X 1",
            title="Bad",
            credits=3,
            offered_terms=["FALL"],
            typical_capacity=10,
        )


# ---------------------------------------------------------------------------
# Generated SQL
# ---------------------------------------------------------------------------
def test_seed_sql_is_generated_and_matches_the_catalog(
    source_catalog: Catalog,
) -> None:
    seed_sql = Path(FIXTURE_PATH).parent / "seed.sql"
    assert seed_sql.exists(), "run: python -m ripplepath.export_fixtures"
    assert seed_sql.read_text(encoding="utf-8") == render_seed_sql(source_catalog)


def test_schema_sql_defines_every_table() -> None:
    schema = (Path(FIXTURE_PATH).parent / "schema.sql").read_text(encoding="utf-8")
    for table in (
        "programs",
        "courses",
        "prerequisites",
        "degree_requirements",
        "registration_state",
        "student_states",
    ):
        assert f"create table if not exists {table}" in schema


def test_schema_forbids_non_synthetic_students() -> None:
    """Compliance guard rail enforced in the database, not just in code."""
    schema = (Path(FIXTURE_PATH).parent / "schema.sql").read_text(encoding="utf-8")
    assert "check (synthetic = true)" in schema


def test_sql_literals_escape_quotes() -> None:
    from ripplepath.export_fixtures import _sql_literal

    assert _sql_literal("O'Brien") == "'O''Brien'"
    assert _sql_literal(["a", "b"]) == "ARRAY['a', 'b']::text[]"
    assert _sql_literal(True) == "true"
    assert _sql_literal(7) == "7"
