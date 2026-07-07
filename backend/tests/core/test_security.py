"""密码哈希与 JWT 单元测试。"""

import pytest
from jose import ExpiredSignatureError, JWTError, jwt

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class TestPassword:
    def test_hash_and_verify_roundtrip(self):
        hashed = hash_password("s3cret-pass")
        assert hashed != "s3cret-pass"
        assert verify_password("s3cret-pass", hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("s3cret-pass")
        assert not verify_password("wrong", hashed)

    def test_malformed_hash_returns_false(self):
        assert not verify_password("whatever", "not-a-bcrypt-hash")


class TestAccessToken:
    def test_roundtrip(self):
        token = create_access_token(42)
        assert decode_access_token(token) == 42

    def test_expired_token_raises(self, monkeypatch):
        monkeypatch.setattr(settings, "jwt_access_token_expire_minutes", -1)
        token = create_access_token(1)
        with pytest.raises(ExpiredSignatureError):
            decode_access_token(token)

    def test_tampered_signature_raises(self):
        token = jwt.encode({"sub": "1"}, "other-secret", algorithm=settings.jwt_algorithm)
        with pytest.raises(JWTError):
            decode_access_token(token)
