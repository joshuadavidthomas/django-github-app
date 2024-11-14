from __future__ import annotations

from threading import Lock


class SequenceGenerator:
    _instance: SequenceGenerator | None = None
    _lock: Lock = Lock()
    _counter: int

    def __init__(self) -> None:
        if not hasattr(self, "_counter"):
            self._counter = 1

    def __new__(cls) -> SequenceGenerator:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def next(self) -> int:
        with self._lock:
            current = self._counter
            self._counter += 1
        return current


seq = SequenceGenerator()
