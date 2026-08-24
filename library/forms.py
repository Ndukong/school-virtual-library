from django import forms
from django.utils.translation import gettext_lazy as _

from library.models import Resource
from library.services import language_code, validate_upload
from schools.models import School


class ResourceForm(forms.ModelForm):
    # Controlled content-language selector. Stored as a normalized code; the
    # clean_language step also accepts legacy free-text spellings (WP7).
    language = forms.CharField(
        required=False,
        widget=forms.Select(
            choices=[("en", _("English")), ("fr", _("French"))],
            attrs={"autocomplete": "off"},
        ),
    )

    class Meta:
        model = Resource
        fields = [
            "title",
            "resource_type",
            "description",
            "subject",
            "school_class",
            "author",
            "publisher",
            "edition",
            "isbn",
            "curriculum",
            "language",
            "publication_year",
            "licensing_status",
            "access_policy",
            "file",
        ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is None or user.is_superuser:
            # Platform superusers choose the owning school explicitly.
            self.fields["school"] = forms.ModelChoiceField(
                queryset=School.objects.all(), required=True
            )
        else:
            # School is fixed server-side for school staff; preset it before
            # validation so cross-school references are caught by model clean.
            self.instance.school = user.school
            self.fields["subject"].queryset = self.fields["subject"].queryset.filter(
                school=user.school
            )
            self.fields["school_class"].queryset = self.fields[
                "school_class"
            ].queryset.filter(school=user.school)
        for name in ("title", "author", "publisher", "edition", "isbn", "curriculum", "language"):
            self.fields[name].widget.attrs.setdefault("autocomplete", "off")

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        if uploaded:
            validate_upload(uploaded)
        return uploaded

    def clean_language(self):
        raw = self.cleaned_data.get("language") or "en"
        code = language_code(raw)
        if not code:
            raise forms.ValidationError(_("Choose English or French as the content language."))
        return code