from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import ListView, TemplateView, View

from accounts.permissions import AdminOrTeacherRequiredMixin, is_admin, is_teacher
from examinations.forms import ExamConfigForm
from examinations.models import Exam
from examinations.services import (
    ExamError,
    assemble_exam,
    mark_ready_for_review,
    publish_exam,
    suggest_fill_from_ai,
    validate_exam,
)
from question_bank.models import Question


class ExamBaseMixin(AdminOrTeacherRequiredMixin):
    def school_scoped_queryset(self):
        if self.request.user.is_superuser:
            return Exam.objects.all()
        return Exam.objects.filter(school=self.request.user.school)

    def get_object(self):
        return get_object_or_404(
            self.school_scoped_queryset().select_related("subject", "school_class", "created_by"),
            public_id=self.kwargs["public_id"],
        )


class ExamListView(ExamBaseMixin, ListView):
    template_name = "examinations/exam_list.html"
    paginate_by = 12

    def get_queryset(self):
        return self.school_scoped_queryset().select_related("subject", "school_class")


class ExamCreateView(ExamBaseMixin, TemplateView):
    template_name = "examinations/exam_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "form" not in context:
            context["form"] = ExamConfigForm(user=self.request.user)
        context["question_types"] = Question.QuestionType.choices
        return context

    def post(self, request):
        form = ExamConfigForm(request.POST, user=request.user)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        exam = form.save(commit=False)
        exam.created_by = request.user
        if request.user.is_superuser:
            exam.school = form.cleaned_data["school"]
        else:
            exam.school = request.user.school
        exam.config = form.to_config()
        try:
            exam.save()
            assemble_exam(exam)
        except ExamError as exc:
            form.add_error(None, str(exc))
            return self.render_to_response(self.get_context_data(form=form))
        messages.success(request, "Exam assembled from approved bank questions.")
        return redirect("exam-detail", public_id=exam.public_id)


class ExamDetailView(ExamBaseMixin, TemplateView):
    template_name = "examinations/exam_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Scope explicitly: TemplateView does not call the mixin get_object.
        exam = get_object_or_404(
            self.school_scoped_queryset()
            .select_related("subject", "school_class", "created_by")
            .prefetch_related("exam_questions__question__subject"),
            public_id=kwargs["public_id"],
        )
        context["exam"] = exam
        context["report"] = validate_exam(exam)
        context["slots"] = list(exam.exam_questions.order_by("position"))
        return context


class ExamActionView(ExamBaseMixin, View):
    """POST-only actions: reassemble / ready / publish / suggest-fill."""

    ACTIONS = {"reassemble", "ready", "publish", "suggest-fill"}

    def post(self, request, public_id, action):
        exam = self.get_object()
        if action not in self.ACTIONS:
            raise Http404("Unknown action.")
        try:
            if action == "reassemble":
                assemble_exam(exam)
                messages.success(request, "Exam re-assembled from the approved bank.")
            elif action == "ready":
                mark_ready_for_review(request.user, exam)
                messages.success(request, "Validation passed; ready for review.")
            elif action == "publish":
                publish_exam(request.user, exam)
                messages.success(request, "Exam published.")
            elif action == "suggest-fill":
                stats = suggest_fill_from_ai(request.user, exam)
                messages.success(
                    request,
                    f"AI suggested {stats['suggested']} candidate question(s); "
                    "review and approve them in the Question Bank, then re-assemble.",
                )
        except ExamError as exc:
            messages.error(request, str(exc))
        except Exception as exc:  # noqa: BLE001 - provider/network failures
            messages.error(request, f"AI service problem: {exc}")
        return redirect("exam-detail", public_id=exam.public_id)


def _staff_can_view(user, exam):
    return user.is_authenticated and (
        user.is_superuser
        or (exam.school_id == user.school_id and (is_admin(user) or is_teacher(user)))
    )


def exam_print_view(request, public_id, with_answers=False):
    """Printable paper (and answer key). Staff-only like every exam view."""
    if not request.user.is_authenticated:
        return redirect(f"{reverse('login')}?next={request.get_full_path()}")
    exam = get_object_or_404(
        Exam.objects.select_related("subject", "school_class").prefetch_related(
            "exam_questions__question"
        ),
        public_id=public_id,
    )
    if not _staff_can_view(request.user, exam):
        raise Http404("Exam not found.")
    slots = list(exam.exam_questions.order_by("position"))
    template = (
        "examinations/exam_print_answers.html" if with_answers
        else "examinations/exam_print.html"
    )
    return render(request, template, {"exam": exam, "slots": slots})