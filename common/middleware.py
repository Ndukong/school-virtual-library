"""Shared middleware.

IdleSessionMiddleware logs out users whose session has been idle past
SESSION_IDLE_SECONDS (shared lab machines, AGENTS section 6).
"""

import time

from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import resolve_url

SESSION_KEY_LAST_SEEN = "_last_seen"


class IdleSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return self.get_response(request)

        session = getattr(request, "session", None)
        if session is None:
            return self.get_response(request)

        idle_seconds = int(getattr(settings, "SESSION_IDLE_SECONDS", 1800))
        now = int(time.time())
        last_seen = session.get(SESSION_KEY_LAST_SEEN)

        if last_seen is not None and (now - last_seen) > idle_seconds:
            from django.contrib.auth import logout

            logout(request)
            login_url = resolve_url(settings.LOGIN_URL)
            from urllib.parse import quote

            return HttpResponseRedirect(f"{login_url}?next={quote(request.get_full_path())}")

        session[SESSION_KEY_LAST_SEEN] = now
        return self.get_response(request)