from __future__ import annotations

import pytest


def test_automatically_skip():
    pytest.fail("tests in `integration` directory should be automatically skipped")
