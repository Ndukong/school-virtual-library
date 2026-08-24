"""Account security services (WP3).

Login lockout: exponential backoff keyed on username AND IP; every failure is
audited in `LoginFailure`; an active `LoginLock` row is checked before the
authentication backend is even asked. Admins can clear locks per user.

Password resets: admins issue a temporary password (returned once for the
credential slip), set `must_change_password`, and record the audit in
`PasswordReset`. `complete_password_change` applies a validated new password
and clears the flag plus the pending reset record.
"""

import secrets

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import LoginFailure, LoginLock, PasswordReset

# ---------------------------------------------------------------------------
# Login lockout
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Admin password resets: temp password, forced change, audit
# ---------------------------------------------------------------------------

_TEMP_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"


def generate_temporary_password(length=12):
    """Generate a usable temporary password (no confusing characters)."""
    return "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(length))


def reset_password(admin_user, target_user):
    """Issue a temporary password; returns the plaintext once for the
    credential slip. Records who reset whom in PasswordReset."""
    while True:
        temporary = generate_temporary_password()
        try:
            validate_password(temporary, user=target_user)
            break
        except ValidationError:
            continue
    target_user.set_password(temporary)
    target_user.must_change_password = True
    target_user.save(update_fields=["password", "must_change_password"])
    PasswordReset.objects.create(target_user=target_user, admin_user=admin_user)
    return temporary


def complete_password_change(user, new_password):
    """Validate + apply a password, clearing the forced-change flag."""
    validate_password(new_password, user=user)
    user.set_password(new_password)
    user.must_change_password = False
    user.save(update_fields=["password", "must_change_password"])
    PasswordReset.objects.filter(target_user=user, completed_at__isnull=True).update(
        completed_at=timezone.now()
    )
