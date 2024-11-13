from __future__ import annotations

import asyncio
import datetime
import itertools
from threading import Thread

import pytest

from .utils import seq


@pytest.fixture(autouse=True)
def clear_seq_state():
    seq._instances = {}
    seq._locks = {}
    yield
    seq._instances = {}
    seq._locks = {}


def test_basic_number_sequence():
    assert seq(1000) == 1001
    assert seq(1000) == 1002
    assert seq(1000) == 1003


def test_string_sequence_with_suffix():
    assert seq("User-", suffix="-test") == "User-1-test"
    assert seq("User-", suffix="-test") == "User-2-test"
    assert seq("User-", suffix="-test") == "User-3-test"


def test_custom_start():
    assert seq("User-", start=10) == "User-10"
    assert seq("User-", start=10) == "User-11"
    assert seq("User-", start=10) == "User-12"


def test_custom_increment():
    assert seq(1000, increment_by=10) == 1010
    assert seq(1000, increment_by=10) == 1020
    assert seq(1000, increment_by=10) == 1030


def test_datetime_sequence():
    start_date = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    increment = datetime.timedelta(days=1)

    assert seq(start_date, increment_by=increment) == datetime.datetime(
        2024, 1, 2, tzinfo=datetime.timezone.utc
    )
    assert seq(start_date, increment_by=increment) == datetime.datetime(
        2024, 1, 3, tzinfo=datetime.timezone.utc
    )


def test_date_sequence():
    start = datetime.date(2024, 1, 1)
    increment = datetime.timedelta(days=1)

    assert seq(start, increment_by=increment) == datetime.date(2024, 1, 2)
    assert seq(start, increment_by=increment) == datetime.date(2024, 1, 3)


def test_time_sequence():
    start = datetime.time(12, 0)
    increment = datetime.timedelta(hours=1)

    assert seq(start, increment_by=increment) == datetime.time(13, 0)
    assert seq(start, increment_by=increment) == datetime.time(14, 0)


def test_float_sequence():
    assert seq(1.5, increment_by=0.5) == 2.0
    assert seq(1.5, increment_by=0.5) == 2.5
    assert seq(1.5, increment_by=0.5) == 3.0


def test_same_value_diff_increment_by():
    assert seq(1000, increment_by=1) == 1001
    assert seq(1000, increment_by=2) == 1002
    assert seq(1000, increment_by=1) == 1002
    assert seq(1000, increment_by=2) == 1004


def test_same_value_diff_suffix():
    assert seq("User-", suffix="-test1") == "User-1-test1"
    assert seq("User-", suffix="-test2") == "User-1-test2"
    assert seq("User-", suffix="-test1") == "User-2-test1"
    assert seq("User-", suffix="-test2") == "User-2-test2"


def test_invalid_suffix():
    with pytest.raises(
        TypeError, match="Sequences with suffix can only be used with text values"
    ):
        seq(1000, suffix="-test")


def test_invalid_datetime_increment():
    start_date = datetime.datetime.now(datetime.timezone.utc)
    with pytest.raises(TypeError, match="increment_by must be a datetime.timedelta"):
        seq(start_date, increment_by=1)


def test_safety_threads():
    results: list[int] = []
    num_threads = 50
    iterations_per_thread = 100

    def worker():
        for _ in range(iterations_per_thread):
            results.append(seq(1000))

    threads = [Thread(target=worker) for _ in range(num_threads)]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == num_threads * iterations_per_thread
    assert len(set(results)) == len(results)
    assert sorted(results) == list(range(1001, 1001 + len(results)))


@pytest.mark.asyncio
async def test_safety_async():
    results: list[int] = []
    num_tasks = 50
    iterations_per_task = 100

    async def worker():
        for _ in range(iterations_per_task):
            results.append(seq(1000))
            # Simulate some async work
            await asyncio.sleep(0.001)

    tasks = [asyncio.create_task(worker()) for _ in range(num_tasks)]
    await asyncio.gather(*tasks)

    assert len(results) == num_tasks * iterations_per_task
    assert len(set(results)) == len(results)
    assert sorted(results) == list(range(1001, 1001 + len(results)))


def test_multiple_sequences_threads():
    results1 = []
    results2 = []
    num_threads = 20

    def worker1():
        results1.append(seq(1000))

    def worker2():
        results2.append(seq(2000))

    threads = []
    for _ in range(num_threads):
        t1 = Thread(target=worker1)
        t2 = Thread(target=worker2)
        threads.extend([t1, t2])
        t1.start()
        t2.start()

    for t in threads:
        t.join()

    assert len(results1) == num_threads
    assert len(set(results1)) == len(results1)
    assert sorted(results1) == list(range(1001, 1001 + len(results1)))

    assert len(results2) == num_threads
    assert len(set(results2)) == len(results2)
    assert sorted(results2) == list(range(2001, 2001 + len(results2)))


@pytest.mark.asyncio
async def test_multiple_sequences_async():
    results1 = []
    results2 = []
    num_tasks = 20

    async def worker1():
        results1.append(seq(1000))
        # Simulate some async work
        await asyncio.sleep(0.001)

    async def worker2():
        results2.append(seq(2000))
        # Simulate some async work
        await asyncio.sleep(0.001)

    tasks = []
    for _ in range(num_tasks):
        tasks.append(asyncio.create_task(worker1()))
        tasks.append(asyncio.create_task(worker2()))

    await asyncio.gather(*tasks)

    assert len(results1) == num_tasks
    assert len(set(results1)) == len(results1)
    assert sorted(results1) == list(range(1001, 1001 + len(results1)))

    assert len(results2) == num_tasks
    assert len(set(results2)) == len(results2)
    assert sorted(results2) == list(range(2001, 2001 + len(results2)))


@pytest.mark.asyncio
async def test_multiple_sequences_async_complex():
    num_tasks = 20
    results_number = []
    results_string = []
    results_date = []

    start_date = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)

    async def worker_number():
        results_number.append(seq(1000))
        await asyncio.sleep(0.001)

    async def worker_string():
        results_string.append(seq("User-", suffix="-test"))
        await asyncio.sleep(0.001)

    async def worker_date():
        results_date.append(seq(start_date, increment_by=datetime.timedelta(days=1)))
        await asyncio.sleep(0.001)

    tasks = []
    for _ in range(num_tasks):
        tasks.extend(
            [
                asyncio.create_task(worker_number()),
                asyncio.create_task(worker_string()),
                asyncio.create_task(worker_date()),
            ]
        )

    await asyncio.gather(*tasks)

    assert len(results_number) == num_tasks
    assert len(set(results_number)) == len(results_number)
    assert sorted(results_number) == list(range(1001, 1001 + len(results_number)))

    assert len(results_string) == num_tasks
    assert len(set(results_string)) == len(results_string)
    assert sorted(results_string) == sorted(
        [f"User-{i}-test" for i in range(1, num_tasks + 1)]
    )

    assert len(results_date) == num_tasks
    assert len(set(results_date)) == len(results_date)
    assert sorted(results_date) == [
        start_date + datetime.timedelta(days=i) for i in range(1, num_tasks + 1)
    ]


def test_sequence_iterator():
    cycled = itertools.cycle(seq.iter(1))
    assert next(cycled) == 2
    assert next(cycled) == 3
    assert next(cycled) == 4
