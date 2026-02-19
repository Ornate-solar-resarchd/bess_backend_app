from __future__ import annotations

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    project_name: str = Field(default="BESS Lifecycle Service", alias="PROJECT_NAME")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")

    database_url: str = Field(alias="DATABASE_URL")
    sql_echo: bool = Field(default=False, alias="SQL_ECHO")
    auto_create_tables: bool = Field(default=False, alias="AUTO_CREATE_TABLES")

    secret_key: str = Field(
        default="replace-with-a-long-random-secret",
        validation_alias=AliasChoices("SECRET_KEY", "JWT_SECRET_KEY"),
    )
    algorithm: str = Field(
        default="HS256",
        validation_alias=AliasChoices("ALGORITHM", "JWT_ALGORITHM"),
    )
    access_token_expire_minutes: int = Field(
        default=30,
        validation_alias=AliasChoices("ACCESS_TOKEN_EXPIRE_MINUTES", "JWT_ACCESS_TOKEN_EXPIRE_MINUTES"),
    )
    refresh_token_expire_days: int = Field(default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    media_root: str = Field(default="./media", validation_alias=AliasChoices("MEDIA_ROOT", "QRCODE_STORAGE_DIR"))
    qr_code_base_url: str = Field(
        default="https://yourdomain.com", validation_alias=AliasChoices("QR_CODE_BASE_URL", "QR_BASE_URL")
    )
    cors_origins: list[str] = Field(default_factory=lambda: ["*"], alias="CORS_ORIGINS")

    default_admin_email: str = Field(default="admin@bess.com", alias="DEFAULT_ADMIN_EMAIL")
    default_admin_password: str = Field(default="Admin@1234", alias="DEFAULT_ADMIN_PASSWORD")

    @field_validator("secret_key", mode="before")
    @classmethod
    def fallback_secret_key(cls, value: str | None) -> str:
        if value:
            return value
        return "replace-with-a-long-random-secret"

    @field_validator("algorithm", mode="before")
    @classmethod
    def fallback_algorithm(cls, value: str | None) -> str:
        if value:
            return value
        return "HS256"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str] | None) -> list[str]:
        if value is None:
            return ["*"]
        if isinstance(value, list):
            return value
        return [item.strip() for item in value.split(",") if item.strip()]

settings = Settings()
