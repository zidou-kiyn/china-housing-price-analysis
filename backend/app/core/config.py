from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/housing_price"
    database_url_sync: str = "postgresql://postgres:postgres@localhost:5432/housing_price"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    crawl_request_delay_min: float = 1.0
    crawl_request_delay_max: float = 3.0
    crawl_max_retries: int = 3

    ml_model_dir: str = "models"

    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
