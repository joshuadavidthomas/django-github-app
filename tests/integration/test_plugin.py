from __future__ import annotations

import pytest

from tests.plugins.integration import CLI_FLAG


def test_automatically_skip(request):
    if not request.config.getoption(CLI_FLAG):
        pytest.fail("tests in `integration` directory should be automatically skipped")
