from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central runtime configuration, read from the environment / .env.local.

    The Supabase defaults are the CLI's public local-dev values so a fresh
    clone works against `supabase start` with zero configuration. Point the
    env vars at a real project to deploy.
    """

    supabase_url: str = "http://127.0.0.1:54321"
    # The Supabase CLI's well-known local development secret key — public,
    # identical for every local stack, and useless against any hosted project.
    supabase_secret_key: str = "sb_secret_N7UND0UgjKTVK-Uodkm0Hg_xSvEMPvz"

    chat_model: str = "gpt-4.1-mini"
    discovery_model: str = "gpt-5.4"
    embed_model: str = "text-embedding-3-small"

    rocchio_alpha: float = 1.0
    rocchio_beta: float = 0.75
    rocchio_gamma: float = 0.15

    # Total extraction rounds allowed per thread (first run + re-extracts).
    max_iterations: int = 3

    model_config = SettingsConfigDict(
        env_file=".env.local", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
