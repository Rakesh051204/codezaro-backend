import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import get_db, Base

# Use a test database (SQLite in‑memory)
TEST_DATABASE_URL = "sqlite:///./test.db"

@pytest.fixture(scope="function")
async def client():
    # Create test database engine
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create tables
    Base.metadata.create_all(bind=engine)

    # Override database dependency
    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Provide an async test client
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    # Cleanup
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()