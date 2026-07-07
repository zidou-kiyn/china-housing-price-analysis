"""管理端用户管理 API 集成测试（封禁/启用、删除、搜索筛选）。"""

import uuid

import pytest
import pytest_asyncio

from tests.api.conftest import _delete_users, _register_and_login

pytestmark = [pytest.mark.slow, pytest.mark.asyncio(loop_scope="session")]


@pytest_asyncio.fixture(loop_scope="session")
async def target_user(client):
    """创建一个待管理的普通用户，返回 (id, username, headers)。"""
    username = f"t_mgmt_{uuid.uuid4().hex[:8]}"
    headers = await _register_and_login(client, username)
    resp = await client.get("/api/v1/auth/me", headers=headers)
    yield resp.json()["id"], username, headers
    await _delete_users([username])


async def _my_id(client, headers) -> int:
    resp = await client.get("/api/v1/auth/me", headers=headers)
    return resp.json()["id"]


class TestStatusToggle:
    async def test_ban_then_unban(self, client, admin_headers, target_user):
        user_id, _, user_headers = target_user

        resp = await client.patch(
            f"/api/v1/admin/users/{user_id}/status",
            json={"is_active": False},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

        # 被封禁用户携旧 token 访问需登录接口 → 403
        resp = await client.get("/api/v1/auth/me", headers=user_headers)
        assert resp.status_code == 403
        assert resp.json()["code"] == "PERMISSION_DENIED"

        # 启用后恢复
        resp = await client.patch(
            f"/api/v1/admin/users/{user_id}/status",
            json={"is_active": True},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        resp = await client.get("/api/v1/auth/me", headers=user_headers)
        assert resp.status_code == 200

    async def test_cannot_ban_self(self, client, admin_headers):
        admin_id = await _my_id(client, admin_headers)
        resp = await client.patch(
            f"/api/v1/admin/users/{admin_id}/status",
            json={"is_active": False},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    async def test_status_forbidden_for_user(self, client, auth_headers, target_user):
        user_id, _, _ = target_user
        resp = await client.patch(
            f"/api/v1/admin/users/{user_id}/status",
            json={"is_active": False},
            headers=auth_headers,
        )
        assert resp.status_code == 403

    async def test_nonexistent_user_404(self, client, admin_headers):
        resp = await client.patch(
            "/api/v1/admin/users/99999999/status",
            json={"is_active": False},
            headers=admin_headers,
        )
        assert resp.status_code == 404


class TestDelete:
    async def test_delete_user(self, client, admin_headers, target_user):
        user_id, username, _ = target_user

        resp = await client.delete(f"/api/v1/admin/users/{user_id}", headers=admin_headers)
        assert resp.status_code == 204

        # 再次登录该账号提示凭证无效
        resp = await client.post(
            "/api/v1/auth/login", json={"username": username, "password": "secret123"}
        )
        assert resp.status_code == 401

        # 列表中检索不到
        resp = await client.get(
            f"/api/v1/admin/users?keyword={username}", headers=admin_headers
        )
        assert resp.json()["total"] == 0

    async def test_cannot_delete_self(self, client, admin_headers):
        admin_id = await _my_id(client, admin_headers)
        resp = await client.delete(f"/api/v1/admin/users/{admin_id}", headers=admin_headers)
        assert resp.status_code == 400

    async def test_delete_forbidden_for_user(self, client, auth_headers, target_user):
        user_id, _, _ = target_user
        resp = await client.delete(f"/api/v1/admin/users/{user_id}", headers=auth_headers)
        assert resp.status_code == 403

    async def test_nonexistent_user_404(self, client, admin_headers):
        resp = await client.delete("/api/v1/admin/users/99999999", headers=admin_headers)
        assert resp.status_code == 404


class TestListFilters:
    async def test_keyword_matches_username_and_email(self, client, admin_headers, target_user):
        _, username, _ = target_user

        resp = await client.get(
            f"/api/v1/admin/users?keyword={username}", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["username"] == username

        # 邮箱模糊匹配（邮箱为 {username}@example.com）
        resp = await client.get(
            f"/api/v1/admin/users?keyword={username}%40example", headers=admin_headers
        )
        assert resp.json()["total"] == 1

    async def test_role_and_status_filters_combined(self, client, admin_headers, target_user):
        user_id, username, _ = target_user

        resp = await client.get(
            f"/api/v1/admin/users?keyword={username}&role=user&is_active=true",
            headers=admin_headers,
        )
        assert resp.json()["total"] == 1

        # 封禁后 is_active=true 过滤不再命中，is_active=false 命中
        await client.patch(
            f"/api/v1/admin/users/{user_id}/status",
            json={"is_active": False},
            headers=admin_headers,
        )
        resp = await client.get(
            f"/api/v1/admin/users?keyword={username}&is_active=true", headers=admin_headers
        )
        assert resp.json()["total"] == 0
        resp = await client.get(
            f"/api/v1/admin/users?keyword={username}&is_active=false", headers=admin_headers
        )
        assert resp.json()["total"] == 1

        # role 不匹配时无结果
        resp = await client.get(
            f"/api/v1/admin/users?keyword={username}&role=admin", headers=admin_headers
        )
        assert resp.json()["total"] == 0

    async def test_invalid_role_param_422(self, client, admin_headers):
        resp = await client.get("/api/v1/admin/users?role=superuser", headers=admin_headers)
        assert resp.status_code == 422

    async def test_pagination_with_filter(self, client, admin_headers):
        resp = await client.get(
            "/api/v1/admin/users?page=1&page_size=1", headers=admin_headers
        )
        data = resp.json()
        assert resp.status_code == 200
        assert len(data["items"]) == 1
        assert data["total"] >= 1
