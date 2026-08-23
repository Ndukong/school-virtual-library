"""Login lockout services (WP3).

Exponential backoff keyed on username AND IP. Every failure is audited in
`LoginFailure`; an active `LoginLock` row is checked before authentication is
even attempted. Admins can clear locks per user (`reset_user_locks`).
"""

from django.conf import settings
from django.utils import timezone

from accounts.models import LoginFailure, LoginLock


def normalize_username(username):
    return (username or "").strip().lower()


def client_ip(request):
    return request.META.get("REMOTE_ADDR", "")


def check_login_lock(username, ip):
    """Return (blocked, wait_seconds) for the username+IP key."""
    if not (username or "").strip():
        return False, 0
    lock = LoginLock.objects.filter(username=normalize_username(username), ip=ip).first()
    if lock and lock.locked_until and timezone.now() < lock.locked_until:
        wait = max(1, int((lock.locked_until - timezone.now()).total_seconds()))
        return True, wait
    return False, 0


def _backoff(attempts):
    base = getattr(settings, "LOGIN_LOCKOUT_BASE_SECONDS", 5)
    maximum = getattr(settings, "LOGIN_LOCKOUT_MAX_SECONDS", 300)
    return min(base * (2 ** (attempts - 1)), maximum)


def record_failed_login(username, ip):
    """Audit the failure and extend the lock with exponential backoff."""
    norm = normalize_username(username)
    if not norm:
        return
    LoginFailure.objects.create(username=norm, ip=ip)
    lock, _ = LoginLock.objects.get_or_create(username=norm, ip=ip)
    lock.attempts += 1
    lock.locked_until = timezone.now() + timezone.timedelta(seconds=_backoff(lock.attempts))
    lock.save(update_fields=["attempts", "locked_until", "updated_at"])


def reset_login_state(username, ip):
    norm = normalize_username(username)
    LoginFailure.objects.filter(username=norm, ip=ip).delete()
    LoginLock.objects.filter(username=norm, ip=ip).delete()


def reset_user_locks(username):
    """Admin unlock: clear every lock and failure record for a user."""
    norm = normalize_username(username)
    LoginFailure.objects.filter(username=norm).delete()
    LoginLock.objects.filter(username=norm).delete()