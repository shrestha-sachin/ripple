"""ripplepath - the Ripple resilience routing engine.

Layer separation is deliberate and enforced by module boundaries:

* ``models``          - domain types shared by every layer.
* ``catalog_source``  - hand-transcribed public catalog data (Phase 1).
* ``repository``      - Supabase / offline-fixture access (Phase 1).
* ``graph``           - NetworkX dependency structure and blast radius (Phase 1).
* ``solver``          - CP-SAT feasibility and repair (Phase 2+).

The CP-SAT solver is the only component permitted to decide whether a plan is
feasible. Graph code answers "what depends on what"; it never rules on legality.
"""

from ripplepath.graph import blast_radius, build_graph, graph_signature
from ripplepath.models import Catalog, Course, Prerequisite, StudentState
from ripplepath.repository import FixtureRepository, SupabaseRepository, load_catalog

__all__ = [
    "Catalog",
    "Course",
    "FixtureRepository",
    "Prerequisite",
    "StudentState",
    "SupabaseRepository",
    "blast_radius",
    "build_graph",
    "graph_signature",
    "load_catalog",
]
