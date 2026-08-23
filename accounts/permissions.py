"""Centralized role checks and access mixins.

All role/permission decisions live here rather than being scattered across
views and templates (AGENTS.md section 9).
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from accounts.models import User


def has_role(user, role):
    """True when an authenticated user holds exactly the given role."""
    return user.is_authenticated and user.role == role


def is_admin(user):
    """Administrators: users with the ADMIN role, plus platform superusers."""
    return user.is_authenticated and (
        user.is_superuser or user.role == User.Role.ADMIN
    )


def is_teacher(user):
    """Teachers hold the TEACHER role exactly; superusers are admins only."""
    return (
        user.is_authenticated
        and not user.is_superuser
        and user.role == User.Role.TEACHER
    )


def is_student(user):
    """Students hold the STUDENT role exactly; superusers are admins only."""
    return (
        user.is_authenticated
        and not user.is_superuser
        and user.role == User.Role.STUDENT
    )


class RoleRequiredMixin(LoginRequiredMixin):
    """Allow only authenticated users holding the required role.

    Anonymous users are redirected to login by LoginRequiredMixin; users with
    the wrong role receive 403 Forbidden. Superusers pass only the ADMIN gate.
    """

    required_role = None

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and self.required_role is not None:
            if self.required_role == User.Role.ADMIN:
                allowed = is_admin(request.user)
            elif self.required_role == User.Role.TEACHER:
                allowed = is_teacher(request.user)
            else:
                allowed = is_student(request.user)
            if not allowed:
                raise PermissionDenied("You do not have permission to view this page.")
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(RoleRequiredMixin):
    required_role = User.Role.ADMIN


class TeacherRequiredMixin(RoleRequiredMixin):
    required_role = User.Role.TEACHER


class StudentRequiredMixin(RoleRequiredMixin):
    required_role = User.Role.STUDENT


class AdminOrTeacherRequiredMixin(RoleRequiredMixin):
    """Allow administrators (incl. superusers) and teachers only."""

    required_role = None

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not (
            is_admin(request.user) or is_teacher(request.user)
        ):
            raise PermissionDenied("You do not have permission to perform this action.")
        return super().dispatch(request, *args, **kwargs)