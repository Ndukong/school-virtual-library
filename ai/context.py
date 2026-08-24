"""Context-var plumbing so AIRequestLog rows carry the school (WP5 budgets)."""

from contextlib import contextmanager
from contextvars import ContextVar

_school = ContextVar("ai_current_school", default=None)


def current_school():
    return _school.get()


@contextmanager
def school_context(school):
    token = _school.set(school)
    try:
        yield
    finally:
        _school.reset(token)