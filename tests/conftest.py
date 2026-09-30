import pytest

from usdbrl_lab.common.config import load_config


@pytest.fixture(scope="session")
def cfg():
    return load_config()
