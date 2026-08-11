"""Data access: Supabase in production, a local JSON fixture for demo safety.

Both repositories return the identical ``Catalog`` model, which is what lets the
Phase 1 parity test assert the two produce byte-identical prerequisite graphs.
If Supabase is unreachable mid-demo, ``load_catalog`` falls back to the fixture
rather than failing - a network blip must never break a live demo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

import httpx

from ripplepath.models import Catalog

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "seed" / "fixtures.json"

# Table name -> the Catalog field it populates.
TABLES: dict[str, str] = {
    "programs": "programs",
    "courses": "courses",
    "prerequisites": "prerequisites",
    "degree_requirements": "degree_requirements",
    "registration_state": "registration_state",
    "student_states": "student_states",
}


class CatalogRepository(Protocol):
    """Anything that can produce a full catalog snapshot."""

    name: str

    def load(self) -> Catalog: ...


class FixtureRepository:
    """Reads the catalog from ``seed/fixtures.json``.

    This is the offline-mode source and the demo-safety net.
    """

    name = "fixture"

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or FIXTURE_PATH

    def load(self) -> Catalog:
        if not self.path.exists():
            raise FileNotFoundError(
                f"offline fixture missing at {self.path}. "
                "Run: python -m ripplepath.export_fixtures"
            )
        with self.path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        return Catalog.model_validate(payload)


class SupabaseRepository:
    """Reads the catalog from Supabase via the PostgREST endpoint.

    Uses the REST API rather than a Postgres driver to keep the container small
    and avoid a native dependency next to OR-Tools' binaries.
    """

    name = "supabase"

    def __init__(self, url: str, service_key: str, timeout: float = 10.0) -> None:
        if not url or not service_key:
            raise ValueError("Supabase URL and service key are both required")
        self.base_url = url.rstrip("/")
        self.service_key = service_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Accept": "application/json",
        }

    def load(self) -> Catalog:
        payload: dict[str, list[dict[str, Any]]] = {}
        with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
            for table, field in TABLES.items():
                response = client.get(
                    f"{self.base_url}/rest/v1/{table}",
                    params={"select": "*"},
                )
                response.raise_for_status()
                payload[field] = response.json()
        return Catalog.model_validate(payload)


def load_catalog(
    *,
    offline: bool,
    supabase_url: str = "",
    supabase_service_key: str = "",
) -> tuple[Catalog, str]:
    """Load the catalog, preferring Supabase but never failing the demo.

    Returns:
        The catalog and the name of the source that actually served it, so
        ``/health`` can tell the truth about where data came from.
    """
    if not offline and supabase_url and supabase_service_key:
        try:
            repo = SupabaseRepository(supabase_url, supabase_service_key)
            return repo.load(), repo.name
        except Exception:
            # Demo safety: fall through to the fixture rather than raising.
            fixture = FixtureRepository()
            return fixture.load(), "fixture-fallback"

    fixture = FixtureRepository()
    return fixture.load(), fixture.name
