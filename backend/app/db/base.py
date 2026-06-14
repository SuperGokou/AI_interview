"""数据库连接与会话(单一职责:engine / SessionLocal / Base / get_db)。"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(database_url: str):
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            future=True,
        )
    # Postgres (e.g. Supabase). Robust parse: last '@' splits creds from host,
    # first ':' splits user from password — tolerates special chars in password.
    scheme, rest = database_url.split("://", 1)
    userinfo, hostpart = rest.rsplit("@", 1)
    user, _, password = userinfo.partition(":")
    hostport, _, dbpart = hostpart.partition("/")
    host, _, port_s = hostport.partition(":")
    database = (dbpart.split("?", 1)[0]) or "postgres"
    port = int(port_s) if port_s else 5432
    url = URL.create(
        "postgresql+psycopg",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database,
    )
    # sslmode=require for Supabase; prepare_threshold=None disables prepared
    # statements so the connection works through the Supabase pooler (pgbouncer
    # transaction mode) as well as the session pooler — needed on IPv4-only hosts
    # like Render (the IPv6 direct host db.<ref>.supabase.co is unreachable there).
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"sslmode": "require", "prepare_threshold": None},
        future=True,
    )


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """创建所有表(开发期用;生产用迁移)。导入 models 以注册映射。"""
    from app.db import models  # noqa: F401  确保模型已注册到 Base.metadata
    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖:每请求一个会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
