import pytest

from app import ratelimit


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    ratelimit.reset()
    yield
    ratelimit.reset()
