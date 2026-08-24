from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


class ForcePasswordChangeForm(forms.Form):
    """First-login password change for users with a temporary password."""

    new_password1 = forms.CharField(
        label="New password", widget=forms.PasswordInput(render_value=False)
    )
    new_password2 = forms.CharField(
        label="Confirm new password", widget=forms.PasswordInput(render_value=False)
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        cleaned = super().clean()
        first = cleaned.get("new_password1")
        second = cleaned.get("new_password2")
        if first and second and first != second:
            self.add_error("new_password2", "The two passwords do not match.")
        if first and self.user:
            try:
                validate_password(first, user=self.user)
            except ValidationError as exc:
                self.add_error("new_password1", exc)
        return cleaned