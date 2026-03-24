import pytest
from fastapi.testclient import TestClient

from src.main import create_app


@pytest.fixture
def tmp_data(tmp_path):
    return tmp_path


@pytest.fixture
def client(tmp_data):
    app = create_app(data_dir=tmp_data)
    with TestClient(app) as c:
        yield c
