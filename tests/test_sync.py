from __future__ import annotations

from typing import Any

import pytest

from django_github_app._sync import async_to_sync_method


class TestAsyncToSyncMethod:
    @pytest.mark.parametrize(
        "return_value",
        [
            "test",
            None,
            {"key": ["value"]},
            (1, "two", 3.0),
        ],
    )
    def test_return(self, return_value: Any):
        class TestClass:
            async def async_method(self) -> Any:
                return return_value

            sync_method = async_to_sync_method(async_method)

        obj = TestClass()
        assert obj.sync_method() == return_value

    def test_method_with_args(self):
        class TestClass:
            async def async_method(
                self, arg: str, *, kwarg: int = 0
            ) -> tuple[str, int]:
                return arg, kwarg

            sync_method = async_to_sync_method(async_method)

        obj = TestClass()
        assert obj.sync_method("test", kwarg=1) == ("test", 1)

    def test_error_propagation(self):
        class TestClass:
            async def async_method(self) -> None:
                raise ValueError("test error")

            sync_method = async_to_sync_method(async_method)

        obj = TestClass()
        with pytest.raises(ValueError, match="test error"):
            obj.sync_method()

    def test_preserves_docstring(self):
        class TestClass:
            async def async_method(self) -> str:
                """Test docstring."""
                return "test"

            sync_method = async_to_sync_method(async_method)

        assert TestClass.sync_method.__doc__ == "Test docstring."

    def test_inheritance(self):
        class BaseClass:
            async def async_method(self) -> str:
                return "base"

        class ChildClass(BaseClass):
            sync_method = async_to_sync_method(BaseClass.async_method)

        obj = ChildClass()
        assert obj.sync_method() == "base"
