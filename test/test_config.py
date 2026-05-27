from app.core.config import Settings


def test_settings_loads_complete_deployment_environment_file(tmp_path, monkeypatch):
    for key in (
        "DATABASE_URL",
        "DATABASE_SEARCH_PATH",
        "CATASTRO_ADMIN_USER",
        "CATASTRO_ADMIN_PASSWORD",
        "CATASTRO_AUTH_SECRET",
        "CATASTRO_AUTH_TTL_MINUTES",
        "CORS_ALLOWED_ORIGINS",
        "CORS_ALLOW_LAN",
    ):
        monkeypatch.delenv(key, raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DATABASE_URL=postgresql+asyncpg://postgres:secret@localhost:5432/avalix_db",
                "DATABASE_SEARCH_PATH=public,extensions",
                "CATASTRO_ADMIN_USER=admin_beta",
                "CATASTRO_ADMIN_PASSWORD=strong-password",
                "CATASTRO_AUTH_SECRET=strong-auth-secret",
                "CATASTRO_AUTH_TTL_MINUTES=120",
                "CORS_ALLOWED_ORIGINS=https://demo.example.com",
                "CORS_ALLOW_LAN=false",
            ]
        ),
        encoding="utf-8",
    )

    configured = Settings(_env_file=env_file)

    assert configured.DATABASE_SEARCH_PATH == "public,extensions"
    assert configured.CATASTRO_ADMIN_USER == "admin_beta"
    assert configured.CATASTRO_ADMIN_PASSWORD == "strong-password"
    assert configured.CATASTRO_AUTH_SECRET == "strong-auth-secret"
    assert configured.CATASTRO_AUTH_TTL_MINUTES == 120
    assert configured.cors_allowed_origins[-1] == "https://demo.example.com"
    assert configured.cors_origin_regex is None
