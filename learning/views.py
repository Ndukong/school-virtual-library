from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import ListView, TemplateView, View

from accounts.permissions import StudentRequiredMixin
from examinations.models import Exam
from learning.forms import QuizStartForm
from learning.models import AttemptResponse, PracticeAttempt
from learning.services import (
    PracticeError,
    get_owned_attempt,
    progress_summary,
    record_self_mark,
    recommend_topics,
    start_from_exam,
    start_quiz,
    student_class_id,
    submit_attempt,
)


def _available_exams(student):
    queryset = Exam.objects.filter(school=student.school, status=Exam.Status.PUBLISHED)
    class_id = student_class_id(student)
    if class_id:
        from django.db.models import Q

        queryset = queryset.filter(
            Q(school_class=class_id) | Q(school_class__isnull=True)
        )
    return queryset.select_related("subject", "school_class")


class PracticeHomeView(StudentRequiredMixin, TemplateView):
    template_name = "learning/practice_home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.pop("form", None) or QuizStartForm(student=self.request.user)
        context["exams"] = _available_exams(self.request.user)
        context["recent_attempts"] = PracticeAttempt.objects.filter(
            student=self.request.user
        )[:8]
        return context


class QuizStartView(StudentRequiredMixin, View):
    def post(self, request):
        form = QuizStartForm(request.POST, student=request.user)
        if not form.is_valid():
            messages.error(request, "Please choose a valid quiz setup.")
            return redirect("practice-home")
        try:
            attempt = start_quiz(
                request.user,
                subject=form.cleaned_data.get("subject") or None,
                topic=form.cleaned_data.get("topic") or "",
                size=form.cleaned_data.get("size"),
            )
        except PracticeError as exc:
            messages.error(request, str(exc))
            return redirect("practice-home")
        return redirect("attempt-page", public_id=attempt.public_id)


class ExamPracticeStartView(StudentRequiredMixin, View):
    def post(self, request):
        exam = get_object_or_404(Exam, public_id=request.POST.get("exam") or "")
        try:
            attempt = start_from_exam(request.user, exam)
        except PracticeError as exc:
            messages.error(request, str(exc))
            return redirect("practice-home")
        return redirect("attempt-page", public_id=attempt.public_id)


class AttemptPageView(StudentRequiredMixin, TemplateView):
    """In-progress attempt: questions and options only - never answers."""

    template_name = "learning/attempt_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            attempt = get_owned_attempt(self.request.user, kwargs["public_id"])
        except PermissionDenied:
            raise Http404("Attempt not found.")
        context["attempt"] = attempt
        context["responses"] = list(attempt.responses.select_related("question"))
        return context


class AttemptSubmitView(StudentRequiredMixin, View):
    def post(self, request, public_id):
        try:
            attempt = get_owned_attempt(request.user, public_id)
            answers = {
                key: value for key, value in request.POST.items()
                if key.startswith("answer_")
            }
            # Map "answer_<pk>" keys to response pks.
            mapped = {}
            for key, value in answers.items():
                mapped[key.replace("answer_", "")] = value
            submit_attempt(attempt, mapped)
        except PermissionDenied:
            raise Http404("Attempt not found.")
        except PracticeError as exc:
            messages.error(request, str(exc))
            return redirect("attempt-page", public_id=public_id)
        return redirect("attempt-result", public_id=attempt.public_id)


class AttemptResultView(StudentRequiredMixin, TemplateView):
    """Post-submission: full explanations, marking schemes, self-marking."""

    template_name = "learning/attempt_result.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            attempt = get_owned_attempt(self.request.user, kwargs["public_id"])
        except PermissionDenied:
            raise Http404("Attempt not found.")
        context["attempt"] = attempt
        context["responses"] = list(
            attempt.responses.select_related("question", "question__subject")
        )
        return context


class ResponseSelfMarkView(StudentRequiredMixin, View):
    def post(self, request, pk):
        response = get_object_or_404(
            AttemptResponse.objects.select_related("attempt", "question"), pk=pk
        )
        value = request.POST.get("correct")
        try:
            record_self_mark(request.user, response, is_correct=(value == "true"))
        except (PermissionDenied, PracticeError) as exc:
            messages.error(request, str(exc))
        return redirect(
            "attempt-result", public_id=response.attempt.public_id
        )


class ProgressView(StudentRequiredMixin, TemplateView):
    template_name = "learning/progress.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(progress_summary(self.request.user))
        context["recommendations"] = recommend_topics(self.request.user)
        return context