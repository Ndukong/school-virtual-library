"""Shared middleware.

IdleSessionMiddleware logs out users whose session has been idle past
SESSION_IDLE_SECONDS (shared lab machines, AGENTS section 6).

MustChangePasswordMiddleware forces users with a temporary password to change
it before using the rest of the platform (their only allowed pages are the
change page and logout).

UserLanguageMiddleware activates the signed-in user's saved language (WP7);
it runs after LocaleMiddleware so the saved preference beats the session.
"""

import time

from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import resolve_url
from django.utils import translation

SESSION_KEY_LAST_SEEN = "_last_seen"

_ALLOWED_PREFIXES = ("/static/", "/admin/")
_ALLOWED_PATHS = ("/password/change/", "/logout/", "/logout-all/", "/login/", "/language/")


class MustChangePasswordMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated and getattr(user, "must_change_password", False):
            path = request.path
            if path in _ALLOWED_PATHS or path.startswith(_ALLOWED_PREFIXES):
                return self.get_response(request)
            return HttpResponseRedirect(resolve_url("force-password-change"))
        return self.get_response(request)


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


def _valid_language_codes():
    lang_codes = {code for code, _label in getattr(settings, "LANGUAGES", [])}
    primary = (getattr(settings, "LANGUAGE_CODE", "en") or "en").split("-")[0]
    return lang_codes | {primary}


class UserLanguageMiddleware:
    """Activate the authenticated user's saved language for this request.

    Order matters: Django's LocaleMiddleware runs earlier and picks the
    language cookie / Accept-Language header; this middleware overrides it
    with the user's own preference so a signed-in student keeps their
    language across devices. Anonymous requests keep the cookie behaviour.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        valid = _valid_language_codes()
        language = ""
        if getattr(request, "user", None) and getattr(request.user, "is_authenticated", False):
            preference = getattr(request.user, "language", "")
            if preference and preference.split("-")[0] in valid:
                language = preference.split("-")[0]
        if not language:
            cookie_language = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME, "")
            if cookie_language and cookie_language.split("-")[0] in valid:
                language = cookie_language.split("-")[0]
        if not language:
            language = (settings.LANGUAGE_CODE or "en").split("-")[0]

        translation.activate(language)
        request.LANGUAGE_CODE = language
        response = self.get_response(request)
        if hasattr(response, "setdefault"):
            response.setdefault("Content-Language", language)
        return response
