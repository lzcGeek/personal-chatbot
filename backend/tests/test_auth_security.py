from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.auth_service import AuthService, normalize_username, token_hash


def test_username_normalization_is_case_insensitive_and_nfkc() -> None:
    assert normalize_username("  Ａlice  ") == "alice"


def test_passwords_are_argon2id_hashed_not_base64_encoded() -> None:
    service = AuthService(session_factory=None, session_ttl_hours=24)  # type: ignore[arg-type]
    encoded = service.password_hash.hash("correct horse battery staple")

    assert encoded.startswith("$argon2id$")
    assert "correct horse battery staple" not in encoded
    assert service.password_hash.verify("correct horse battery staple", encoded)


def test_session_and_csrf_tokens_are_only_compared_by_hash() -> None:
    csrf = "browser-csrf-token"
    session = SimpleNamespace(csrf_hash=token_hash(csrf))
    service = object.__new__(AuthService)

    assert token_hash(csrf) != csrf
    assert service.verify_csrf(session, csrf, csrf)
    assert not service.verify_csrf(session, csrf, "different")
    assert not service.verify_csrf(session, None, csrf)


def test_new_session_uses_distinct_random_tokens() -> None:
    service = AuthService(session_factory=None, session_ttl_hours=24)  # type: ignore[arg-type]
    now = datetime.now(timezone.utc)
    first = service._new_session(now)
    second = service._new_session(now)

    assert first.token != second.token
    assert first.csrf_token != second.csrf_token
    assert first.expires_at > now
