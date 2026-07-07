"""鉴权与权限 API 集成测试。"""

import uuid

import pytest
import pytest_asyncio

from tests.api.conftest import _delete_users

pytestmark = [pytest.mark.slow, pytest.mark.asyncio(loop_scope="session")]


@pytest_asyncio.fixture(loop_scope="session")
async def temp_username():
    username = f"t_reg_{uuid.uuid4().hex[:8]}"
    yield username
    await _delete_users([username])


def _register_payload(username: str) -> dict:
    return {"username": username, "email": f"{username}@example.com", "password": "secret123"}


class TestRegister:
    async def test_register_success(self, client, temp_username):
        resp = await client.post("/api/v1/auth/register", json=_register_payload(temp_username))
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == temp_username
        assert data["role"] == "user"
        assert "password" not in data

    async def test_duplicate_username(self, client, temp_username):
        await client.post("/api/v1/auth/register", json=_register_payload(temp_username))
        payload = _register_payload(temp_username)
        payload["email"] = f"other_{temp_username}@example.com"
        resp = await client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 409
        assert resp.json()["code"] == "USERNAME_EXISTS"

    async def test_duplicate_email(self, client, temp_username):
        await client.post("/api/v1/auth/register", json=_register_payload(temp_username))
        payload = _register_payload(f"t_reg_{uuid.uuid4().hex[:8]}")
        payload["email"] = f"{temp_username}@example.com"
        resp = await client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 409
        assert resp.json()["code"] == "EMAIL_EXISTS"

    async def test_short_password_rejected(self, client):
        payload = _register_payload(f"t_reg_{uuid.uuid4().hex[:8]}")
        payload["password"] = "123"
        resp = await client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 422


class TestLogin:
    async def test_login_success(self, client, temp_username):
        await client.post("/api/v1/auth/register", json=_register_payload(temp_username))
        resp = await client.post(
            "/api/v1/auth/login", json={"username": temp_username, "password": "secret123"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["token_type"] == "bearer"
        assert data["access_token"]

    async def test_wrong_password(self, client, temp_username):
        await client.post("/api/v1/auth/register", json=_register_payload(temp_username))
        resp = await client.post(
            "/api/v1/auth/login", json={"username": temp_username, "password": "wrong"}
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == "INVALID_CREDENTIALS"

    async def test_nonexistent_user(self, client):
        resp = await client.post(
            "/api/v1/auth/login", json={"username": "no_such_user_xyz", "password": "whatever"}
        )
        assert resp.status_code == 401


class TestMe:
    async def test_me_with_token(self, client, auth_headers):
        resp = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "user"
        assert data["is_active"] is True

    async def test_me_without_token(self, client):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401
        assert resp.json()["code"] == "TOKEN_INVALID"

    async def test_me_with_garbage_token(self, client):
        resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})
        assert resp.status_code == 401
        assert resp.json()["code"] == "TOKEN_INVALID"


class TestPermissions:
    async def test_compare_requires_auth(self, client):
        resp = await client.get("/api/v1/compare?region_type=district&region_ids=1,2")
        assert resp.status_code == 401

    async def test_map_heat_requires_auth(self, client):
        resp = await client.get("/api/v1/map/heat?city_code=qz")
        assert resp.status_code == 401

    async def test_rank_stays_public(self, client):
        resp = await client.get("/api/v1/rank?region_type=city")
        assert resp.status_code == 200

    async def test_admin_users_forbidden_for_user(self, client, auth_headers):
        resp = await client.get("/api/v1/admin/users", headers=auth_headers)
        assert resp.status_code == 403
        assert resp.json()["code"] == "PERMISSION_DENIED"

    async def test_admin_users_ok_for_admin(self, client, admin_headers):
        resp = await client.get("/api/v1/admin/users", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert all("username" in u for u in data["items"])


class TestRoleUpdate:
    async def test_admin_can_change_role(self, client, admin_headers, temp_username):
        resp = await client.post("/api/v1/auth/register", json=_register_payload(temp_username))
        user_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/admin/users/{user_id}/role", json={"role": "admin"}, headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    async def test_invalid_role_rejected(self, client, admin_headers, temp_username):
        resp = await client.post("/api/v1/auth/register", json=_register_payload(temp_username))
        user_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/admin/users/{user_id}/role", json={"role": "superuser"}, headers=admin_headers
        )
        assert resp.status_code == 422

    async def test_nonexistent_user_404(self, client, admin_headers):
        resp = await client.patch(
            "/api/v1/admin/users/99999999/role", json={"role": "user"}, headers=admin_headers
        )
        assert resp.status_code == 404
