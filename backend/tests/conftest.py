import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.base import Base, get_db


@pytest.fixture
def _engine():
    # StaticPool + 单一内存连接:让所有 session 共享同一个内存库,
    # 这样 db_session 里 seed 的数据,client 走 API 能读到。
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def _SessionLocal(_engine):
    return sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def client(_engine, _SessionLocal):
    def override_get_db():
        db = _SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def db_session(_SessionLocal):
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
