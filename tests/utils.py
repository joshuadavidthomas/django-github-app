from __future__ import annotations

import datetime
import warnings
from collections.abc import Iterator
from threading import Lock
from typing import Any

EPOCH = datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc)


class seq:
    """A thread-safe sequence generator that mimics model-bakery's seq functionality.

    This class provides a way to generate sequential values for use in tests, particularly
    with Django models and model-bakery. Unlike model-bakery's seq, this implementation
    is thread-safe and works reliably in async/concurrent test environments.

    The class maintains separate sequences for different parameter combinations using
    class-level state, protected by locks for thread safety. It supports numbers,
    strings, dates, times, and datetimes.

    Examples:
        Simple number sequence:
        >>> seq(1000)
        1001
        >>> seq(1000)
        1002
        >>> seq(1000)
        1003

        String sequence with suffix:
        >>> seq("User-", suffix="-test")
        'User-1-test'
        >>> seq("User-", suffix="-test")
        'User-2-test'

        String sequence with custom start:
        >>> seq("User-", start=10)
        'User-10'
        >>> seq("User-", start=10)
        'User-11'

        Number sequence with custom increment:
        >>> seq(1000, increment_by=10)
        1010
        >>> seq(1000, increment_by=10)
        1020

        DateTime sequence:
        >>> start_date = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
        >>> first = seq(start_date, increment_by=datetime.timedelta(days=1))
        >>> first.isoformat()
        '2024-01-02T00:00:00+00:00'
        >>> second = seq(start_date, increment_by=datetime.timedelta(days=1))
        >>> second.isoformat()
        '2024-01-03T00:00:00+00:00'

        Date sequence:
        >>> start = datetime.date(2024, 1, 1)
        >>> first = seq(start, increment_by=datetime.timedelta(days=1))
        >>> str(first)
        '2024-01-02'
        >>> second = seq(start, increment_by=datetime.timedelta(days=1))
        >>> str(second)
        '2024-01-03'

        Time sequence:
        >>> start = datetime.time(12, 0)
        >>> first = seq(start, increment_by=datetime.timedelta(hours=1))
        >>> str(first)
        '13:00:00'
        >>> second = seq(start, increment_by=datetime.timedelta(hours=1))
        >>> str(second)
        '14:00:00'
    """

    _instances = {}
    _locks = {}

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

        if key not in cls._locks:
            # Use a temporary lock to protect lock creation
            with Lock():
                if key not in cls._locks:
                    cls._locks[key] = Lock()

        with cls._locks[key]:
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
    def iter(
        cls,
        value: Any,
        increment_by: int | float | datetime.timedelta = 1,
        start: int | float | None = None,
        suffix: str | None = None,
    ) -> Iterator[Any]:
        while True:
            yield cls(value, increment_by=increment_by, start=start, suffix=suffix)
