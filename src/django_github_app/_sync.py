from __future__ import annotations

import functools
from collections.abc import Coroutine
from typing import Any
from typing import Callable
from typing import ParamSpec
from typing import TypeVar

from asgiref.sync import async_to_sync

P = ParamSpec("P")
T = TypeVar("T")


def async_to_sync_method(
    async_func: Callable[P, Coroutine[Any, Any, T]],
) -> Callable[P, T]:
    @functools.wraps(async_func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        return async_to_sync(async_func)(*args, **kwargs)

    return wrapper
