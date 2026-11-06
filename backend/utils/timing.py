"""Timing and request logging, so slow steps are easy to find.

  @timed('groq_parse')              logs how long one function takes
  @timed('analyze_total', summary=True)
                                    also logs one summary line listing every timed step that
                                    ran inside it, slowest first
  install_request_timing(app)       logs method, path, status and duration of every request

Steps under SLOW_STEP_SECONDS go to the log file only (INFO). Slower ones are logged as
WARNING, so they also show up in the terminal window.
"""

import asyncio
import contextvars
import functools
import logging
import time

logger = logging.getLogger('ats_resume_scorer')

SLOW_STEP_SECONDS = 5.0
SLOW_REQUEST_SECONDS = 10.0

_current = contextvars.ContextVar('step_timings', default=None)


def _record(name: str, seconds: float) -> None:
    steps = _current.get()
    if steps is not None:
        steps[name] = steps.get(name, 0.0) + seconds
    if seconds >= SLOW_STEP_SECONDS:
        logger.warning(f'SLOW STEP {name} took {seconds:.2f}s')
    else:
        logger.info(f'TIMING {name} {seconds:.2f}s')


def _finish(name: str, start: float, token, summary: bool) -> None:
    elapsed = time.perf_counter() - start
    steps = None
    if summary:
        steps = _current.get()
        _current.reset(token)
    _record(name, elapsed)
    if summary and steps:
        parts = ' | '.join(f'{k} {v:.2f}s' for k, v in sorted(steps.items(), key=lambda kv: -kv[1]))
        logger.info(f'TIMING SUMMARY {name} {elapsed:.2f}s -> {parts}')


def timed(name: str, summary: bool = False):
    """Decorator for sync and async functions."""
    def decorator(fn):
        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                token = _current.set({}) if summary else None
                start = time.perf_counter()
                try:
                    return await fn(*args, **kwargs)
                finally:
                    _finish(name, start, token, summary)
            return async_wrapper

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            token = _current.set({}) if summary else None
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                _finish(name, start, token, summary)
        return wrapper
    return decorator


def install_request_timing(app) -> None:
    """Log every HTTP request with its status code and duration (no query strings, no bodies)."""
    @app.middleware('http')
    async def _timing_middleware(request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.error(f'REQUEST {request.method} {request.url.path} crashed after {time.perf_counter() - start:.2f}s')
            raise
        elapsed = time.perf_counter() - start
        message = f'REQUEST {request.method} {request.url.path} {response.status_code} {elapsed:.2f}s'
        if elapsed >= SLOW_REQUEST_SECONDS:
            logger.warning(f'SLOW {message}')
        else:
            logger.info(message)
        return response
