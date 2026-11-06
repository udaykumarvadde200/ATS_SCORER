import asyncio
import logging
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.utils import timing
from backend.utils.timing import install_request_timing, timed


@pytest.fixture(autouse=True)
def _capture(caplog):
    caplog.set_level(logging.INFO, logger='ats_resume_scorer')


def messages(caplog):
    return [r.getMessage() for r in caplog.records]


def test_timed_returns_the_value_and_logs_the_step(caplog):
    @timed('add_step')
    def add(a, b=1):
        return a + b

    assert add(2, b=3) == 5
    assert any(m.startswith('TIMING add_step ') for m in messages(caplog))


def test_exceptions_pass_through_and_are_still_timed(caplog):
    @timed('failing_step')
    def boom():
        raise ValueError('nope')

    with pytest.raises(ValueError):
        boom()
    assert any('failing_step' in m for m in messages(caplog))


def test_async_functions_are_supported(caplog):
    @timed('async_step')
    async def work():
        await asyncio.sleep(0)
        return 'done'

    assert asyncio.run(work()) == 'done'
    assert any('async_step' in m for m in messages(caplog))


def test_summary_lists_inner_steps_slowest_first(caplog):
    @timed('inner_fast')
    def fast():
        return 1

    @timed('inner_slow')
    def slow():
        time.sleep(0.05)
        return 2

    @timed('outer', summary=True)
    def outer():
        return fast() + slow()

    assert outer() == 3
    summary = [m for m in messages(caplog) if m.startswith('TIMING SUMMARY outer')][0]
    assert summary.index('inner_slow') < summary.index('inner_fast')


def test_slow_steps_are_warnings(caplog, monkeypatch):
    monkeypatch.setattr(timing, 'SLOW_STEP_SECONDS', 0.0)

    @timed('slow_one')
    def f():
        return None

    f()
    assert any(r.levelno == logging.WARNING and 'SLOW STEP slow_one' in r.getMessage() for r in caplog.records)


def test_request_middleware_logs_method_path_and_status(caplog):
    app = FastAPI()
    install_request_timing(app)

    @app.get('/ping')
    def ping():
        return {'ok': True}

    assert TestClient(app).get('/ping?secret=1').status_code == 200
    line = [m for m in messages(caplog) if m.startswith('REQUEST')][0]
    assert 'GET /ping 200' in line and 'secret' not in line
