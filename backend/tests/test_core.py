"""Тесты app/core/* (config, security, logging)."""

from __future__ import annotations

import pytest

from app.core.config import Settings, get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

# ---------- config ----------


def test_settings_defaults():
    get_settings.cache_clear()
    s = get_settings()
    assert s.app_name == "askk-prototype"
    assert s.app_env in ("dev", "test", "staging", "prod")
    assert s.api_port == 8000
    assert s.geo_radius_m == 75


def test_settings_cors_origins_list():
    get_settings.cache_clear()
    s = get_settings()
    s.cors_origins = "http://a, http://b , http://c"
    assert s.cors_origins_list == ["http://a", "http://b", "http://c"]


def test_settings_cors_origins_strip():
    get_settings.cache_clear()
    s = get_settings()
    s.cors_origins = "  http://x  "
    assert s.cors_origins_list == ["http://x"]


def test_settings_cors_origins_empty():
    s = Settings(cors_origins="")
    assert s.cors_origins_list == []


# ---------- security: passwords ----------


def test_hash_password_format():
    h = hash_password("secret")
    assert h.startswith("$2")


def test_hash_password_unique_salts():
    assert hash_password("same") != hash_password("same")


def test_verify_password_correct():
    assert verify_password("secret", hash_password("secret")) is True


def test_verify_password_wrong():
    assert verify_password("secret", hash_password("other")) is False


def test_verify_password_invalid_hash():
    assert verify_password("secret", "not-a-bcrypt-hash") is False


def test_verify_password_empty_hash():
    assert verify_password("secret", "") is False


# ---------- security: tokens ----------


def test_create_access_token_has_payload():
    token = create_access_token("user-1", extra={"role": "manager"})
    payload = decode_token(token)
    assert payload["sub"] == "user-1"
    assert payload["type"] == "access"
    assert payload["role"] == "manager"
    assert "iat" in payload and "exp" in payload


def test_create_access_token_no_extra():
    token = create_access_token(42)
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["type"] == "access"
    assert "role" not in payload


def test_create_refresh_token():
    token = create_refresh_token("user-1")
    payload = decode_token(token)
    assert payload["sub"] == "user-1"
    assert payload["type"] == "refresh"


def test_decode_token_invalid():
    with pytest.raises(ValueError, match="Invalid token"):
        decode_token("garbage.token.value")


def test_decode_token_wrong_signature():
    # Token signed with different key
    from jose import jwt

    bad = jwt.encode({"sub": "x", "type": "access"}, "different-key", algorithm="HS256")
    with pytest.raises(ValueError, match="Invalid token"):
        decode_token(bad)


# ---------- logging ----------


def test_setup_logging_runs_twice():
    from app.core.logging import get_logger, setup_logging

    setup_logging()
    setup_logging()  # idempotent
    log = get_logger("test")
    assert log is not None


def test_get_logger_with_name():
    from app.core.logging import get_logger

    log = get_logger("my.module")
    assert log is not None


def test_get_logger_with_initial_context():
    from app.core.logging import get_logger

    log = get_logger("ctx", request_id="abc")
    assert log is not None


def test_setup_logging_levels():
    from app.core import logging as clog

    clog.setup_logging()
    # Just check that level is set without error
    assert clog.get_logger("x") is not None
