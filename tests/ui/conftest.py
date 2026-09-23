import pytest

from quietsql.ui.app import create_app
from quietsql.ui.fake_services import build_fake_services


@pytest.fixture
def fake_services():
    return build_fake_services(token_delay=0.0)


@pytest.fixture
def app_with_fakes(fake_services):
    create_app(fake_services)
    return fake_services
