from __future__ import annotations

from pathlib import Path

import pytest

MARK = "integration"
CLI_FLAG = "--integration"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add the --integration flag to pytest CLI.

    Args:
        parser: pytest parser.
    """
    parser.addoption(
        CLI_FLAG, action="store_true", help="run integration tests as well"
    )


def pytest_configure(config: pytest.Config) -> None:
    """Add the integration marker to pytest config.

    Args:
        config: pytest config.
    """
    config.addinivalue_line("markers", f"{MARK}: mark tests as integration tests")


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Do not run tests marked as integration tests by default, unless a flag is set.

    Args:
        item: pytest's test item.
    """
    if MARK in item.keywords and not item.config.getoption(CLI_FLAG):
        pytest.skip(f"pass {CLI_FLAG} to run integration tests")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Marks tests in the integration folder as end-to-end tests (which will not run by default).

    Args:
        config: pytest configuration.
        items: Items to test (individual tests).
    """
    integration_dir = Path(__file__).parent.parent / "integration"
    for item in items:
        if Path(item.fspath).parent == integration_dir:
            item.add_marker(MARK)
