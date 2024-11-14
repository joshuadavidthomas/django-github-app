from __future__ import annotations

import datetime
import json
import tempfile
import warnings
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from filelock import FileLock

EPOCH = datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc)


class seq:
    """A thread-safe sequence generator that mimics model-bakery's seq functionality.

    This class provides a way to generate sequential values for use in tests, particularly
    with Django models and model-bakery. Unlike model-bakery's seq, this implementation
    is thread-safe and works reliably in async/concurrent test environments.

    The class maintains separate sequences for different parameter combinations using
    class-level state, protected by locks for thread safety. It supports numbers,
    strings, dates, times, and datetimes.
    """

    _instances = {}
    _locks = {}
    _process_lock_file = Path(tempfile.gettempdir(), "seq_process_lock")
    _process_lock = FileLock(_process_lock_file)
    _state_file = Path(tempfile.gettempdir(), "seq_state.json")

    def __init__(
        self,
        value: Any,
        increment_by: int | float | datetime.timedelta = 1,
        start: int | float | None = None,
        suffix: str | None = None,
    ):
        """Initialize sequence parameters."""
        self._validate_parameters(value, increment_by, start, suffix)
        self.value = value
        self.increment_by = increment_by
        self.start = start
        self.suffix = suffix
        self._current = 0
        self._increment = 0
        self._base = None
        self._initialized = False

    def _validate_parameters(
        self,
        value: Any,
        increment_by: int | float | datetime.timedelta,
        start: int | float | None,
        suffix: str | None,
    ) -> None:
        """Validate sequence parameters match model-bakery's requirements."""
        if suffix and not isinstance(value, str):
            raise TypeError("Sequences with suffix can only be used with text values")

        if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
            if not isinstance(increment_by, datetime.timedelta):
                raise TypeError(
                    "Sequences with values datetime.datetime, datetime.date and datetime.time, "
                    "increment_by must be a datetime.timedelta."
                )
            if start:
                warnings.warn(
                    "start parameter is ignored when using seq with date, time or datetime objects",
                    stacklevel=1,
                )

    def __new__(
        cls,
        value: Any,
        increment_by: int | float | datetime.timedelta = 1,
        start: int | float | None = None,
        suffix: str | None = None,
    ):
        key = (value, increment_by, start, suffix)

        # Use process-safe lock for instance creation
        with cls._process_lock:
            if key not in cls._locks:
                cls._locks[key] = cls._get_process_safe_lock(key)

            # Load saved state if instance doesn't exist
            if key not in cls._instances:
                saved_state = cls._load_state()
                if key in saved_state:
                    instance = super().__new__(cls)
                    instance.__init__(value, increment_by, start, suffix)
                    instance._current = saved_state[key]
                    instance._initialized = True
                    cls._instances[key] = instance

        lock = cls._locks[key]
        with lock:
            if key not in cls._instances:
                instance = super().__new__(cls)
                instance.__init__(value, increment_by, start, suffix)
                instance._initialized = True
                if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
                    instance._initialize_datetime_sequence(value, increment_by)
                else:
                    instance._initialize_basic_sequence(value, increment_by, start)
                cls._instances[key] = instance

            instance = cls._instances[key]
            instance._current += instance._increment

            # Save state after updating
            cls._save_state()

            if isinstance(value, (datetime.datetime, datetime.date)):
                return instance._generate_datetime_value()
            elif isinstance(value, datetime.time):
                return instance._generate_time_value()
            elif isinstance(instance._base, (int, float)):
                return instance._generate_numeric_value()
            else:
                return instance._generate_text_value()

    def _initialize_datetime_sequence(
        self,
        value: datetime.datetime | datetime.date | datetime.time,
        increment_by: datetime.timedelta,
    ) -> None:
        if isinstance(value, datetime.datetime):
            date = value
        elif isinstance(value, datetime.date):
            date = datetime.datetime.combine(value, datetime.datetime.now().time())
        else:
            date = datetime.datetime.combine(EPOCH.date(), value)

        epoch = EPOCH.replace(tzinfo=date.tzinfo)
        self._current = (date - epoch).total_seconds()
        self._increment = increment_by.total_seconds()

    def _initialize_basic_sequence(
        self, value: Any, increment_by: Any, start: Any
    ) -> None:
        self._current = 0 if start is None else start - increment_by
        self._increment = increment_by
        self._base = value

    def _generate_time_value(self) -> datetime.time:
        total_seconds = self._current % (24 * 3600)
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        return datetime.time(hours, minutes, seconds)

    def _generate_datetime_value(self) -> datetime.datetime | datetime.date:
        tz = self.value.tzinfo if isinstance(self.value, datetime.datetime) else None
        result = datetime.datetime.fromtimestamp(self._current, tz)

        if isinstance(self.value, datetime.date) and not isinstance(
            self.value, datetime.datetime
        ):
            return result.date()
        return result

    def _generate_numeric_value(self) -> int | float:
        if not isinstance(self._base, (int, float)):
            raise ValueError("base must be a numeric type")
        return self._base + self._current

    def _generate_text_value(self) -> str:
        value = [self._base, self._current]
        if self.suffix:
            value.append(self.suffix)
        stringified_value = [str(v) for v in value]
        return "".join(stringified_value)

    @classmethod
    def _reset(cls):
        """Reset all sequence state. Used for testing purposes."""
        with cls._process_lock:
            cls._instances.clear()
            cls._locks.clear()
            if cls._state_file.exists():
                cls._state_file.unlink()

    @classmethod
    def _load_state(cls):
        """Load sequence state from file."""
        try:
            with cls._process_lock:
                if cls._state_file.exists():
                    state = json.loads(cls._state_file.read_text())
                    return {
                        tuple(json.loads(k)): v.get("_current", 0)
                        for k, v in state.items()
                    }
        except Exception:
            return {}
        return {}

    @classmethod
    def _save_state(cls):
        """Save sequence state to file."""
        with cls._process_lock:
            state = {
                json.dumps([str(k) for k in key]): {"_current": instance._current}
                for key, instance in cls._instances.items()
            }
            cls._state_file.write_text(json.dumps(state))

    @classmethod
    def _get_process_safe_lock(cls, key):
        """Get or create a process-safe lock for the given key."""
        lock_file = Path(tempfile.gettempdir(), f"seq_lock_{hash(key)}")
        return FileLock(lock_file)

    @classmethod
    def iter(
        cls,
        value: Any,
        increment_by: int | float | datetime.timedelta = 1,
        start: int | float | None = None,
        suffix: str | None = None,
    ) -> Iterator[Any]:
        while True:
            yield cls(value, increment_by=increment_by, start=start, suffix=suffix)
