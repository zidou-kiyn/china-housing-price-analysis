import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.main import app
from app.models.city import City


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
