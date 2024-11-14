from __future__ import annotations

import asyncio
import random
import threading
import time

import pytest

from .utils import SequenceGenerator


@pytest.fixture
def seq():
    """Fixture to reset the counter before each test."""
    SequenceGenerator._instance = None
    return SequenceGenerator()


def test_multithreading(seq):
    num_threads = 100
    increments_per_thread = 100

    def worker():
        for _ in range(increments_per_thread):
            seq.next()

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert seq.next() == num_threads * increments_per_thread + 1


@pytest.mark.asyncio
async def test_async(seq):
    num_coroutines = 100
    increments_per_coroutine = 100

    async def worker():
        for _ in range(increments_per_coroutine):
            seq.next()

    await asyncio.gather(*(worker() for _ in range(num_coroutines)))

    assert seq.next() == num_coroutines * increments_per_coroutine + 1


@pytest.mark.asyncio
async def test_combined(seq):
    num_threads = 50
    num_coroutines = 50
    increments_per_thread = 50
    increments_per_coroutine = 50

    def thread_worker():
        for _ in range(increments_per_thread):
            seq.next()

    async def async_worker():
        for _ in range(increments_per_coroutine):
            seq.next()

    threads = [threading.Thread(target=thread_worker) for _ in range(num_threads)]

    for thread in threads:
        thread.start()

    await asyncio.gather(*(async_worker() for _ in range(num_coroutines)))

    for thread in threads:
        thread.join()

    expected_value = (num_threads * increments_per_thread) + (
        num_coroutines * increments_per_coroutine
    )
    assert seq.next() == expected_value + 1


def test_multithreading_with_sequence_validation(seq):
    num_threads = 100
    increments_per_thread = 100
    results: set[int] = set()

    def worker():
        for _ in range(increments_per_thread):
            value = seq.next()
            results.add(value)
            # Random sleep to try to force race conditions
            if random.random() < 0.1:
                time.sleep(0.001)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    expected_set = set(range(1, num_threads * increments_per_thread + 1))
    assert results == expected_set
    assert seq.next() == num_threads * increments_per_thread + 1


@pytest.mark.asyncio
async def test_async_with_sequence_validation(seq):
    num_coroutines = 100
    increments_per_coroutine = 100
    results: set[int] = set()

    async def worker():
        for _ in range(increments_per_coroutine):
            value = seq.next()
            results.add(value)
            # Random sleep to try to force race conditions
            if random.random() < 0.1:
                await asyncio.sleep(0.001)

    await asyncio.gather(*(worker() for _ in range(num_coroutines)))

    expected_set = set(range(1, num_coroutines * increments_per_coroutine + 1))
    assert results == expected_set
    assert seq.next() == num_coroutines * increments_per_coroutine + 1


@pytest.mark.asyncio
async def test_combined_with_sequence_validation(seq):
    num_threads = 50
    num_coroutines = 50
    increments_per_thread = 50
    increments_per_coroutine = 50
    results: set[int] = set()

    def thread_worker():
        for _ in range(increments_per_thread):
            value = seq.next()
            results.add(value)
            if random.random() < 0.1:
                time.sleep(0.001)

    async def async_worker():
        for _ in range(increments_per_coroutine):
            value = seq.next()
            results.add(value)
            if random.random() < 0.1:
                await asyncio.sleep(0.001)

    threads = [threading.Thread(target=thread_worker) for _ in range(num_threads)]

    for thread in threads:
        thread.start()

    await asyncio.gather(*(async_worker() for _ in range(num_coroutines)))

    for thread in threads:
        thread.join()

    expected_total = (num_threads * increments_per_thread) + (
        num_coroutines * increments_per_coroutine
    )
    expected_set = set(range(1, expected_total + 1))
    assert results == expected_set
    assert seq.next() == expected_total + 1


def test_large_scale(seq):
    """Test with a larger number of threads and increments"""
    num_threads = 200
    increments_per_thread = 1000
    results: set[int] = set()

    def worker():
        for _ in range(increments_per_thread):
            value = seq.next()
            results.add(value)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    expected_set = set(range(1, num_threads * increments_per_thread + 1))
    assert results == expected_set
    assert seq.next() == num_threads * increments_per_thread + 1


def test_error_conditions(seq):
    """Test error conditions and edge cases"""
    seq2 = SequenceGenerator()
    assert seq is seq2

    def create_instance():
        SequenceGenerator()

    threads = [threading.Thread(target=create_instance) for _ in range(100)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    instances = [SequenceGenerator() for _ in range(10)]
    assert all(instance is seq for instance in instances)
