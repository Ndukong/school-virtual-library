from django import forms

from question_bank.models import Question
from schools.models import School


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = [
            "subject", "school_class", "topic", "subtopic",
            "question_type", "difficulty", "marks", "bloom_level",
            "body", "options", "correct_answer", "marking_scheme",
            "source_resource", "chapter", "page_number",
        ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is not None:
            if user.is_superuser:
                # Platform staff choose the owning school explicitly.
                self.fields["school"] = forms.ModelChoiceField(
                    queryset=School.objects.all(), required=True
                )
            else:
                school = user.school
                self.instance.school = school
                self.fields["subject"].queryset = self.fields["subject"].queryset.filter(school=school)
                self.fields["school_class"].queryset = self.fields["school_class"].queryset.filter(school=school)
                self.fields["source_resource"].queryset = self.fields["source_resource"].queryset.filter(
                    school=school
                )
                self.fields["chapter"].queryset = self.fields["chapter"].queryset.filter(
                    resource__school=school
                )
        for name in ("topic", "subtopic"):
            self.fields[name].widget.attrs.setdefault("autocomplete", "off")

    def clean_options(self):
        raw = self.cleaned_data.get("options")
        question_type = self.cleaned_data.get("question_type")
        if question_type != Question.QuestionType.MCQ or raw in (None, ""):
            return raw
        if isinstance(raw, str):
            # One option per line from the textarea widget.
            raw = [line.strip() for line in raw.splitlines() if line.strip()]
        return raw
