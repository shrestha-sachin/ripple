from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Ripple API.

    Values are read from environment variables (or a local .env file).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RIPPLE_",
        extra="ignore",
    )

    # Deployment
    environment: str = "development"
    git_sha: str = "local"

    # Demo safety: when true the engine serves data from seed/fixtures.json
    # instead of Supabase, so a network blip can never break a live demo.
    offline: bool = False

    # Comma-separated list of allowed browser origins.
    cors_origins: str = "http://localhost:3000"

    # Supabase (unused in Phase 0, wired in Phase 1)
    supabase_url: str = ""
    supabase_service_key: str = ""

    # Solver time caps in seconds. Enforced so the UI can never hang.
    solver_plan_timeout: float = 10.0
    solver_repair_timeout: float = 3.0
    solver_scenario_timeout: float = 0.5

    # Monte-Carlo stress test
    stress_scenarios: int = 200
    stress_seed: int = 20260810

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
