import pytest
from app.config.settings import settings

@pytest.fixture(scope="session")
def test_settings():
    settings.ALLOWED_TARGETS = ["127.0.0.1", "localhost", "dvwa.local"]
    return settings

@pytest.fixture
def sample_cve_json():
    with open("scripts/fixtures/sample_cve.json", "r", encoding="utf-8") as f:
        return json.load(f)