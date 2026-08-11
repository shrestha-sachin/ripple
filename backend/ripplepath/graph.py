"""NetworkX prerequisite graph.

This layer answers exactly one class of question: *what depends on what*. It
computes blast radius (Phase 4) and earliest feasible terms (a Phase 2 solver
scale guard). It never decides whether a plan is legal - that is CP-SAT's job
alone.

Edge direction is ``prerequisite -> dependent``, so ``networkx.descendants`` is
literally "everything downstream of this course".
"""

from __future__ import annotations

import networkx as nx

from ripplepath.models import Catalog, Course


class PrerequisiteGraphError(ValueError):
    """Raised when the catalog cannot form a valid prerequisite DAG."""


def build_graph(catalog: Catalog) -> nx.DiGraph:
    """Build the prerequisite DAG for a catalog.

    Raises:
        PrerequisiteGraphError: if a prerequisite references an unknown course,
            or if the prerequisite relation contains a cycle. A cycle would make
            the degree unsatisfiable, so failing loudly here beats handing an
            impossible model to the solver.
    """
    graph = nx.DiGraph()
    courses = catalog.course_map()

    for course in catalog.courses:
        graph.add_node(
            course.course_id,
            title=course.title,
            credits=course.credits,
            offered_terms=tuple(course.offered_terms),
            typical_capacity=course.typical_capacity,
        )

    unknown: set[str] = set()
    for row in catalog.prerequisites:
        if row.course_id not in courses:
            unknown.add(row.course_id)
            continue
        if row.requires_course_id not in courses:
            unknown.add(row.requires_course_id)
            continue
        graph.add_edge(
            row.requires_course_id,
            row.course_id,
            relation=row.relation,
            group_id=row.group_id,
        )

    if unknown:
        raise PrerequisiteGraphError(
            f"prerequisites reference courses missing from the catalog: "
            f"{sorted(unknown)}"
        )

    if not nx.is_directed_acyclic_graph(graph):
        cycle = nx.find_cycle(graph, orientation="original")
        raise PrerequisiteGraphError(f"prerequisite graph contains a cycle: {cycle}")

    return graph


def graph_signature(graph: nx.DiGraph) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    """A canonical, order-independent fingerprint of the graph.

    Used by the Supabase/offline parity test: two data sources agree only if
    their graphs have identical node and edge sets.
    """
    nodes = tuple(sorted(graph.nodes))
    edges = tuple(sorted((u, v) for u, v in graph.edges))
    return nodes, edges


def blast_radius(graph: nx.DiGraph, course_id: str) -> set[str]:
    """Every course transitively downstream of ``course_id``.

    This is the set that lights up in the UI when a disruption fires. It is
    intentionally the *graph* answer, not the plan answer - Phase 4 intersects
    it with the student's planned courses.
    """
    if course_id not in graph:
        raise KeyError(f"unknown course {course_id!r}")
    return set(nx.descendants(graph, course_id))


def dependents(graph: nx.DiGraph, course_id: str) -> set[str]:
    """Courses that list ``course_id`` as an immediate prerequisite."""
    if course_id not in graph:
        raise KeyError(f"unknown course {course_id!r}")
    return set(graph.successors(course_id))


def prerequisite_closure(graph: nx.DiGraph, course_ids: set[str]) -> set[str]:
    """``course_ids`` plus everything they transitively require.

    Phase 2 uses this as a scale guard: the CP-SAT model is restricted to the
    degree-relevant closure instead of the entire catalog.
    """
    missing = course_ids - set(graph.nodes)
    if missing:
        raise KeyError(f"unknown courses {sorted(missing)}")
    closure = set(course_ids)
    for course_id in course_ids:
        closure |= nx.ancestors(graph, course_id)
    return closure


def degree_relevant_courses(catalog: Catalog, graph: nx.DiGraph, program: str) -> set[str]:
    """Courses that could plausibly appear in a plan for ``program``."""
    eligible: set[str] = set()
    for requirement in catalog.requirements_for(program):
        eligible.update(requirement.eligible_courses)
    unknown = eligible - set(graph.nodes)
    if unknown:
        raise PrerequisiteGraphError(
            f"degree requirements reference unknown courses: {sorted(unknown)}"
        )
    return prerequisite_closure(graph, eligible)


def topological_depth(graph: nx.DiGraph) -> dict[str, int]:
    """Longest prerequisite-chain length ending at each course.

    Depth 0 means no prerequisites. Depth ``d`` means the course cannot possibly
    start earlier than the student's ``d``-th planning term, which lets Phase 2
    forbid provably-too-early assignments and shrink the search space.
    """
    depth: dict[str, int] = {}
    for course_id in nx.topological_sort(graph):
        preds = list(graph.predecessors(course_id))
        depth[course_id] = 1 + max((depth[p] for p in preds), default=-1)
    return depth


def earliest_feasible_index(
    catalog: Catalog,
    graph: nx.DiGraph,
    completed: set[str],
    terms: list[str],
) -> dict[str, int]:
    """Earliest index into ``terms`` at which each course could be taken.

    Combines two independent lower bounds:

    1. **Chain depth** - a course whose unmet prerequisite chain is ``d`` deep
       needs ``d`` terms of runway first.
    2. **Term offering** - the course must actually be offered that season.

    Courses that can never be scheduled in the horizon are omitted, so the
    solver never creates variables for them.
    """
    courses = catalog.course_map()
    bound: dict[str, int] = {}

    for course_id in nx.topological_sort(graph):
        if course_id in completed:
            bound[course_id] = 0
            continue
        earliest = 0
        for prereq in graph.predecessors(course_id):
            if prereq in completed:
                continue
            # A prerequisite must land strictly before its dependent.
            prereq_bound = bound.get(prereq)
            if prereq_bound is None:
                continue
            earliest = max(earliest, prereq_bound + 1)
        bound[course_id] = earliest

    result: dict[str, int] = {}
    for course_id, lower in bound.items():
        if course_id in completed:
            continue
        course: Course = courses[course_id]
        for index in range(lower, len(terms)):
            if course.offered_in(terms[index]):
                result[course_id] = index
                break
    return result
