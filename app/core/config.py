from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
)

LAN_ORIGIN_REGEX = (
    r"http://("
    r"localhost|127\.0\.0\.1|"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
    r"):\d+"
)


class Settings(BaseSettings):
    PROJECT_NAME: str = "Sistema de Avaluo Catastral"
    VERSION: str = "2.0.0"
    DATABASE_URL: str
    DATABASE_SEARCH_PATH: str = "public"
    CORS_ALLOWED_ORIGINS: str = ""
    CORS_ALLOW_LAN: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_allowed_origins(self) -> list[str]:
        extra_origins = [
            origin.strip().rstrip("/")
            for origin in self.CORS_ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]
        return list(dict.fromkeys([*DEFAULT_CORS_ORIGINS, *extra_origins]))

    @property
    def cors_origin_regex(self) -> str | None:
        return LAN_ORIGIN_REGEX if self.CORS_ALLOW_LAN else None


settings = Settings()
