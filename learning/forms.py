from django import forms

from subjects.models import Subject


class QuizStartForm(forms.Form):
    SIZE_CHOICES = [(3, "3 questions"), (5, "5 questions"), (10, "10 questions")]

    subject = forms.ModelChoiceField(queryset=Subject.objects.none(), required=False)
    topic = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )
    size = forms.TypedChoiceField(choices=SIZE_CHOICES, coerce=int, initial=5)

    def __init__(self, *args, student=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.student = student
        if student is not None and student.school_id:
            self.fields["subject"].queryset = Subject.objects.filter(school=student.school)

    def clean_topic(self):
        return (self.cleaned_data.get("topic") or "").strip()