"""创建或提升管理员账号。

用法：
    .venv/bin/python scripts/create_admin.py <username> <email> <password>   # 创建 admin
    .venv/bin/python scripts/create_admin.py <username>                       # 提升已有用户为 admin
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import UserAccount


async def main() -> None:
    if len(sys.argv) not in (2, 4):
        print(__doc__)
        sys.exit(1)

    username = sys.argv[1]
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        user = (
            await session.execute(select(UserAccount).where(UserAccount.username == username))
        ).scalar_one_or_none()

        if user:
            user.role = "admin"
            await session.commit()
            print(f"已将用户 {username} 提升为 admin")
        elif len(sys.argv) == 4:
            session.add(
                UserAccount(
                    username=username,
                    email=sys.argv[2],
                    password_hash=hash_password(sys.argv[3]),
                    role="admin",
                )
            )
            await session.commit()
            print(f"已创建 admin 用户 {username}")
        else:
            print(f"用户 {username} 不存在；创建新账号需提供 email 与 password")
            sys.exit(1)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
