import pytest
from fastapi.testclient import TestClient

from src.main import create_app
from src.api import deps


@pytest.fixture
def tmp_data(tmp_path):
    return tmp_path


@pytest.fixture
def client(tmp_data):
    # Reset per-user state between tests
    deps._user_vaults.clear()
    deps._user_engines.clear()

    app = create_app(data_dir=tmp_data)
    with TestClient(app) as c:
        yield c

    # Cleanup after test
    deps._user_vaults.clear()
    deps._user_engines.clear()
