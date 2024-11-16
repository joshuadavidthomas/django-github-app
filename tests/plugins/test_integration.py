from __future__ import annotations

from .integration import CLI_FLAG
from .integration import MARK


def test_cli_flag_registered(pytestconfig):
    assert pytestconfig.getoption(CLI_FLAG) in (
        True,
        False,
    ), f"{CLI_FLAG} should be registered with pytest"


def test_markers_registered(pytestconfig):
    markers = pytestconfig.getini("markers")
    assert any(
        f"{MARK}:" in marker for marker in markers
    ), f"{MARK} marker should be registered"
