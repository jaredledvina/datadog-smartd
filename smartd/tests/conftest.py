import pytest

from datadog_checks.smartd import SmartdCheck

from .common import CHECK_NAME, INSTANCE


@pytest.fixture(scope='session')
def dd_environment():
    yield INSTANCE


@pytest.fixture
def check():
    return SmartdCheck(CHECK_NAME, {}, [INSTANCE])
