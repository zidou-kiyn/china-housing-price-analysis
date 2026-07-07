import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.main import app
from app.models.city import City
from app.models.user import UserAccount


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def qz_city_id():
    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as s:
        city = (await s.execute(select(City).where(City.code == "qz"))).scalar_one()
        city_id = city.id
    await engine.dispose()
    return city_id


async def _delete_users(usernames: list[str]) -> None:
    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as s:
        await s.execute(delete(UserAccount).where(UserAccount.username.in_(usernames)))
        await s.commit()
    await engine.dispose()


async def _register_and_login(client: AsyncClient, username: str, role: str = "user") -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "secret123"},
    )
    assert resp.status_code == 201, resp.text

    if role != "user":
        engine = create_async_engine(settings.database_url)
        sf = async_sessionmaker(engine, expire_on_commit=False)
        async with sf() as s:
            user = (
                await s.execute(select(UserAccount).where(UserAccount.username == username))
            ).scalar_one()
            user.role = role
            await s.commit()
        await engine.dispose()

    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "secret123"}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def auth_headers(client):
    username = f"t_user_{uuid.uuid4().hex[:8]}"
    headers = await _register_and_login(client, username)
    yield headers
    await _delete_users([username])


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def admin_headers(client):
    username = f"t_admin_{uuid.uuid4().hex[:8]}"
    headers = await _register_and_login(client, username, role="admin")
    yield headers
    await _delete_users([username])
