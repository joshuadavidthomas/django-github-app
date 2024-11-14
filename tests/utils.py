from __future__ import annotations

from threading import Lock


class SequenceGenerator:
    _instance = None
    _lock = Lock()

    def __init__(self):
        self._counter = 1

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._counter = 1
        return cls._instance

    def next(self):
        with self._lock:
            current = self._counter
            self._counter += 1
        return current


seq = SequenceGenerator()
