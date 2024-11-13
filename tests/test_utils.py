from __future__ import annotations

import asyncio
import datetime
import itertools
from collections import deque
from queue import Queue
from threading import Lock
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
    results_queue: Queue[int] = Queue()
    num_threads = 50
    iterations_per_thread = 100

    def worker():
        local_results = []  # Use thread-local storage first
        for _ in range(iterations_per_thread):
            local_results.append(seq(1000))
        # Bulk transfer to queue
        for result in local_results:
            results_queue.put(result)

    threads = [Thread(target=worker) for _ in range(num_threads)]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Convert queue to list for verification
    results = []
    while not results_queue.empty():
        results.append(results_queue.get())

    assert len(results) == num_threads * iterations_per_thread
    assert len(set(results)) == len(results)
    assert sorted(results) == list(range(1001, 1001 + len(results)))


@pytest.mark.asyncio
async def test_safety_async():
    results = deque(maxlen=num_tasks * iterations_per_task)
    results_lock = Lock()  # For thread-safe deque access
    num_tasks = 50
    iterations_per_task = 100

    async def worker():
        local_results = []  # Local buffer
        for _ in range(iterations_per_task):
            local_results.append(seq(1000))
            await asyncio.sleep(0.001)
        # Bulk transfer with single lock acquisition
        with results_lock:
            results.extend(local_results)

    tasks = [asyncio.create_task(worker()) for _ in range(num_tasks)]
    await asyncio.gather(*tasks)

    results_list = list(results)
    assert len(results_list) == num_tasks * iterations_per_task
    assert len(set(results_list)) == len(results_list)
    assert sorted(results_list) == list(range(1001, 1001 + len(results_list)))


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
    results1: Queue[int] = Queue()
    results2: Queue[int] = Queue()
    num_threads = 20

    def worker1():
        local_results = []
        local_results.append(seq(1000))
        for result in local_results:
            results1.put(result)

    def worker2():
        local_results = []
        local_results.append(seq(2000))
        for result in local_results:
            results2.put(result)

    threads = []
    for _ in range(num_threads):
        t1 = Thread(target=worker1)
        t2 = Thread(target=worker2)
        threads.extend([t1, t2])
        t1.start()
        t2.start()

    for t in threads:
        t.join()

    results1_list = []
    results2_list = []

    while not results1.empty():
        results1_list.append(results1.get())
    while not results2.empty():
        results2_list.append(results2.get())

    assert len(results1_list) == num_threads
    assert len(set(results1_list)) == len(results1_list)
    assert sorted(results1_list) == list(range(1001, 1001 + len(results1_list)))

    assert len(results2_list) == num_threads
    assert len(set(results2_list)) == len(results2_list)
    assert sorted(results2_list) == list(range(2001, 2001 + len(results2_list)))


@pytest.mark.asyncio
async def test_multiple_sequences_async():
    results1_queue = asyncio.Queue()
    results2_queue = asyncio.Queue()
    num_tasks = 20

    async def worker1():
        local_results = []
        local_results.append(seq(1000))
        await asyncio.sleep(0.001)
        await results1_queue.put(local_results[0])

    async def worker2():
        local_results = []
        local_results.append(seq(2000))
        await asyncio.sleep(0.001)
        await results2_queue.put(local_results[0])

    tasks = []
    for _ in range(num_tasks):
        tasks.append(asyncio.create_task(worker1()))
        tasks.append(asyncio.create_task(worker2()))

    await asyncio.gather(*tasks)

    results1 = []
    results2 = []

    while not results1_queue.empty():
        results1.append(await results1_queue.get())
    while not results2_queue.empty():
        results2.append(await results2_queue.get())

    assert len(results1) == num_tasks
    assert len(set(results1)) == len(results1)
    assert sorted(results1) == list(range(1001, 1001 + len(results1)))

    assert len(results2) == num_tasks
    assert len(set(results2)) == len(results2)
    assert sorted(results2) == list(range(2001, 2001 + len(results2)))


@pytest.mark.asyncio
async def test_multiple_sequences_async_complex():
    num_tasks = 20

    number_queue = asyncio.Queue()
    string_queue = asyncio.Queue()
    date_queue = asyncio.Queue()

    start_date = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)

    async def worker_number():
        result = seq(1000)
        await asyncio.sleep(0.001)
        await number_queue.put(result)

    async def worker_string():
        result = seq("User-", suffix="-test")
        await asyncio.sleep(0.001)
        await string_queue.put(result)

    async def worker_date():
        result = seq(start_date, increment_by=datetime.timedelta(days=1))
        await asyncio.sleep(0.001)
        await date_queue.put(result)

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

    results_number = []
    results_string = []
    results_date = []

    async def drain_queue(queue):
        results = []
        while not queue.empty():
            results.append(await queue.get())
        return results

    results_number = await drain_queue(number_queue)
    results_string = await drain_queue(string_queue)
    results_date = await drain_queue(date_queue)

    assert len(results_number) == num_tasks
    assert len(set(results_number)) == len(results_number)
    assert sorted(results_number) == list(range(1001, 1001 + len(results_number)))

    assert len(results_string) == num_tasks
    assert len(set(results_string)) == len(results_string)
    expected_strings = [f"User-{i}-test" for i in range(1, num_tasks + 1)]
    assert sorted(results_string) == sorted(expected_strings)

    assert len(results_date) == num_tasks
    assert len(set(results_date)) == len(results_date)
    expected_dates = [
        start_date + datetime.timedelta(days=i) for i in range(1, num_tasks + 1)
    ]
    assert sorted(results_date) == expected_dates


def test_sequence_iterator():
    cycled = itertools.cycle(seq.iter(1))
    assert next(cycled) == 2
    assert next(cycled) == 3
    assert next(cycled) == 4
