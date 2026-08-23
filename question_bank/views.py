from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView, View

from accounts.permissions import AdminOrTeacherRequiredMixin
from ai.models import AIGeneration
from question_bank.forms import QuestionForm
from question_bank.models import Question
from question_bank.services import (
    WorkflowError,
    approve_question,
    can_manage,
    find_duplicates,
    import_from_ai_generation,
    importable_generations,
    reject_question,
    submit_for_review,
)
from subjects.models import Subject


class QuestionBankBaseMixin(AdminOrTeacherRequiredMixin):
    """Question bank is staff-only: answer keys must not reach students.

    AdminOrTeacherRequiredMixin includes LoginRequiredMixin (anonymous users
    are redirected to login; students receive 403).
    """

    def school_scoped_queryset(self):
        if self.request.user.is_superuser:
            return Question.objects.all()
        return Question.objects.filter(school=self.request.user.school)


class QuestionListView(QuestionBankBaseMixin, ListView):
    template_name = "question_bank/question_list.html"
    paginate_by = 15

    def get_queryset(self):
        queryset = self.school_scoped_queryset().select_related("subject", "school_class", "author")
        params = self.request.GET
        if params.get("subject"):
            queryset = queryset.filter(subject_id=params["subject"])
        if params.get("status"):
            status = params["status"]
            if status in Question.ApprovalStatus.values:
                queryset = queryset.filter(approval_status=status)
        if params.get("type"):
            qtype = params["type"]
            if qtype in Question.QuestionType.values:
                queryset = queryset.filter(question_type=qtype)
        if params.get("q"):
            queryset = queryset.filter(body__icontains=params["q"].strip())
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school = self.request.user.school
        context.update(
            {
                "statuses": Question.ApprovalStatus.choices,
                "question_types": Question.QuestionType.choices,
                "subjects": Subject.objects.filter(school=school) if school else Subject.objects.none(),
                "current": {
                    "subject": self.request.GET.get("subject", ""),
                    "status": self.request.GET.get("status", ""),
                    "type": self.request.GET.get("type", ""),
                    "q": self.request.GET.get("q", ""),
                },
            }
        )
        return context


class QuestionDetailView(QuestionBankBaseMixin, DetailView):
    template_name = "question_bank/question_detail.html"
    slug_field = "public_id"
    slug_url_kwarg = "public_id"

    def get_queryset(self):
        return self.school_scoped_queryset().select_related(
            "subject", "school_class", "author", "approved_by",
            "source_resource", "chapter", "ai_generation",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        question = self.object
        user = self.request.user
        context["can_manage"] = can_manage(user, question)
        context["duplicates"] = find_duplicates(question, exclude_pk=question.pk) if question.pk else []
        return context


class QuestionCreateView(QuestionBankBaseMixin, CreateView):
    model = Question
    form_class = QuestionForm
    template_name = "question_bank/question_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        question = form.save(commit=False)
        question.author = self.request.user
        if self.request.user.is_superuser:
            question.school = form.cleaned_data["school"]
        else:
            question.school = self.request.user.school
        question.save()
        return redirect("question-detail", public_id=question.public_id)


class QuestionUpdateView(QuestionBankBaseMixin, UpdateView):
    model = Question
    form_class = QuestionForm
    template_name = "question_bank/question_form.html"
    slug_field = "public_id"
    slug_url_kwarg = "public_id"

    def get_queryset(self):
        return self.school_scoped_queryset()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        question = form.save(commit=False)
        if not self.request.user.is_superuser:
            question.school = self.request.user.school
        question.save()
        return redirect("question-detail", public_id=question.public_id)


class QuestionActionView(QuestionBankBaseMixin, View):
    """POST-only workflow transitions: submit / approve / reject."""

    def post(self, request, public_id, action):
        question = get_object_or_404(
            self.school_scoped_queryset(), public_id=public_id
        )
        try:
            if action == "submit":
                submit_for_review(request.user, question)
            elif action == "approve":
                approve_question(request.user, question)
            elif action == "reject":
                reject_question(request.user, question, request.POST.get("notes", ""))
            else:
                raise WorkflowError("Unknown action.")
        except WorkflowError as exc:
            from django.contrib import messages

            messages.error(request, str(exc))
        return redirect("question-detail", public_id=question.public_id)


class ImportOptionsView(QuestionBankBaseMixin, TemplateView):
    """List the user's AI practice-question generations available for import."""

    template_name = "question_bank/import_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["generations"] = importable_generations(self.request.user)
        return context


class ImportRunView(QuestionBankBaseMixin, View):
    def post(self, request):
        generation = get_object_or_404(
            AIGeneration, public_id=request.POST.get("generation") or ""
        )
        try:
            stats = import_from_ai_generation(request.user, generation)
        except (ValueError, WorkflowError) as exc:
            from django.contrib import messages

            messages.error(request, str(exc))
            return redirect("question-import")
        from django.contrib import messages

        messages.success(
            request,
            f"Imported {stats['imported']} question(s) into review "
            f"({stats['skipped']} malformed block(s) skipped).",
        )
        return redirect(f"{reverse('question-list')}?status=PENDING_REVIEW")
