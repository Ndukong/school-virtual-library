from django import forms

from examinations.models import Exam
from question_bank.models import Question
from schools.models import School


class ExamConfigForm(forms.ModelForm):
    topics = forms.CharField(
        required=False,
        help_text="Comma-separated topics to cover, e.g. induction, transformers",
    )
    bloom_distribution = forms.CharField(
        required=False,
        help_text="Optional per-level percentages, e.g. KNOWLEDGE=40, APPLICATION=60",
    )
    question_types = forms.MultipleChoiceField(
        required=False,
        choices=Question.QuestionType.choices,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Exam
        fields = [
            "title", "subject", "school_class", "duration_minutes",
            "total_marks", "instructions",
        ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is not None:
            if user.is_superuser:
                self.fields["school"] = forms.ModelChoiceField(
                    queryset=School.objects.all(), required=True
                )
            else:
                school = user.school
                self.instance.school = school
                self.fields["subject"].queryset = self.fields["subject"].queryset.filter(school=school)
                self.fields["school_class"].queryset = self.fields["school_class"].queryset.filter(
                    school=school
                )

    def clean_topics(self):
        raw = self.cleaned_data.get("topics") or ""
        return [t.strip() for t in raw.split(",") if t.strip()]

    def clean_bloom_distribution(self):
        raw = self.cleaned_data.get("bloom_distribution") or ""
        distribution = {}
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            if "=" not in chunk:
                raise forms.ValidationError(
                    f"Use LEVEL=PERCENT entries separated by commas (got '{chunk}')."
                )
            level, _, value = chunk.partition("=")
            level = level.strip().upper()
            if level not in Question.BloomLevel.values:
                raise forms.ValidationError(f"Unknown Bloom level '{level}'.")
            try:
                distribution[level] = max(0.0, min(100.0, float(value)))
            except ValueError:
                raise forms.ValidationError(f"Percent must be numeric (got '{value}').")
        return distribution

    def to_config(self, cleaned=None):
        cleaned = cleaned or self.cleaned_data
        return {
            "topics": cleaned.get("topics") or [],
            "question_types": cleaned.get("question_types") or [],
            "bloom_distribution": cleaned.get("bloom_distribution") or {},
        }
