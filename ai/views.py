from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import ListView, TemplateView

from ai.models import AIGeneration, AIInteraction
from ai.rag import AIError, ask, sources_for
from ai.ratelimit import RateLimited
from ai.study import generate_study_material
from classes.models import SchoolClass
from library.models import BookChapter
from library.services import visible_resources
from subjects.models import Subject


def _scope_context(user):
    school = user.school
    return {
        "subjects": Subject.objects.filter(school=school) if school else Subject.objects.none(),
        "classes": SchoolClass.objects.filter(school=school) if school else SchoolClass.objects.none(),
    }


class AskView(LoginRequiredMixin, TemplateView):
    """Ask the AI Librarian. Scope via query params: ?book=<uuid>&chapter=<id>."""

    template_name = "ai/ask.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request
        book_param = request.GET.get("book") or None
        chapter_param = request.GET.get("chapter") or None

        scope = AIInteraction.Scope.LIBRARY
        scope_target = None
        if chapter_param:
            chapter = (
                BookChapter.objects.select_related("resource")
                .filter(pk=chapter_param).first()
            )
            if chapter and visible_resources(request.user).filter(
                pk=chapter.resource_id
            ).exists():
                scope = AIInteraction.Scope.CHAPTER
                scope_target = chapter
        elif book_param:
            resource = visible_resources(request.user).filter(public_id=book_param).first()
            if resource:
                scope = AIInteraction.Scope.BOOK
                scope_target = resource

        context.update(
            {
                "scope": scope,
                "scope_target": scope_target,
                "book_param": book_param or "",
                "chapter_param": chapter_param or "",
                **_scope_context(request.user),
            }
        )
        if request.GET.get("error"):
            context["error_message"] = request.GET.get("error")
        return context

    def post(self, request, *args, **kwargs):
        question = (request.POST.get("question") or "").strip()
        scope = request.POST.get("scope") or AIInteraction.Scope.LIBRARY
        book_param = request.POST.get("book") or None
        chapter_param = request.POST.get("chapter") or None

        if not question:
            return self._redirect_with_error("Please enter a question.",
                                             book_param, chapter_param)

        try:
            interaction = ask(
                request.user,
                question,
                scope=scope,
                resource_public_id=book_param,
                chapter_id=chapter_param,
            )
        except RateLimited as exc:
            return self._redirect_with_error(str(exc), book_param, chapter_param)
        except ValueError as exc:
            return self._redirect_with_error(str(exc), book_param, chapter_param)
        except AIError:
            # Interaction already recorded with a friendly message.
            pass
        return redirect("ai-answer", public_id=interaction.public_id)

    def _redirect_with_error(self, message, book_param, chapter_param):
        from urllib.parse import quote

        params = {"error": message}
        if book_param:
            params["book"] = book_param
        if chapter_param:
            params["chapter"] = chapter_param
        query = "&".join(f"{k}={quote(v)}" for k, v in params.items())
        return redirect(f"{reverse('ai-ask')}?{query}")


class AnswerView(LoginRequiredMixin, TemplateView):
    """Shows one Q&A pair; only its owner (or a superuser) may view it."""

    template_name = "ai/answer.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        interaction = get_object_or_404(
            AIInteraction, public_id=kwargs["public_id"]
        )
        if interaction.user_id != self.request.user.pk and not self.request.user.is_superuser:
            raise Http404("Answer not found.")
        context["interaction"] = interaction
        context["sources"] = sources_for(interaction)
        return context

class StudyToolView(LoginRequiredMixin, TemplateView):
    """AI study tools: summary / revision notes / definitions / practice."""

    template_name = "ai/study_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request
        book_param = request.GET.get("book") or None
        chapter_param = request.GET.get("chapter") or None

        scope = AIInteraction.Scope.LIBRARY
        scope_target = None
        if chapter_param:
            chapter = (
                BookChapter.objects.select_related("resource")
                .filter(pk=chapter_param).first()
            )
            if chapter and visible_resources(request.user).filter(
                pk=chapter.resource_id
            ).exists():
                scope = AIInteraction.Scope.CHAPTER
                scope_target = chapter
        elif book_param:
            resource = visible_resources(request.user).filter(public_id=book_param).first()
            if resource:
                scope = AIInteraction.Scope.BOOK
                scope_target = resource

        context.update(
            {
                "kinds": AIGeneration.Kind.choices,
                "selected_kind": request.GET.get("kind") or AIGeneration.Kind.SUMMARY,
                "scope": scope,
                "scope_target": scope_target,
                "book_param": book_param or "",
                "chapter_param": chapter_param or "",
                **_scope_context(request.user),
            }
        )
        if request.GET.get("error"):
            context["error_message"] = request.GET.get("error")
        return context

    def post(self, request, *args, **kwargs):
        kind = request.POST.get("kind") or ""
        scope = request.POST.get("scope") or AIInteraction.Scope.LIBRARY
        book_param = request.POST.get("book") or None
        chapter_param = request.POST.get("chapter") or None
        topic = request.POST.get("topic") or ""

        try:
            generation = generate_study_material(
                request.user,
                kind,
                scope=scope,
                resource_public_id=book_param,
                chapter_id=chapter_param,
                topic=topic,
            )
        except ValueError as exc:
            return self._redirect_with_error(str(exc), kind, book_param, chapter_param)
        except RateLimited as exc:
            return self._redirect_with_error(str(exc), kind, book_param, chapter_param)
        except AIError:
            pass  # generation row already records the outage message
        return redirect("ai-study-result", public_id=generation.public_id)

    def _redirect_with_error(self, message, kind, book_param, chapter_param):
        from urllib.parse import quote

        params = {"error": message}
        if kind:
            params["kind"] = kind
        if book_param:
            params["book"] = book_param
        if chapter_param:
            params["chapter"] = chapter_param
        query = "&".join(f"{k}={quote(v)}" for k, v in params.items())
        return redirect(f"{reverse('ai-study')}?{query}")


class StudyResultView(LoginRequiredMixin, TemplateView):
    template_name = "ai/study_result.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        generation = get_object_or_404(AIGeneration, public_id=kwargs["public_id"])
        if generation.user_id != self.request.user.pk and not self.request.user.is_superuser:
            raise Http404("Material not found.")
        context["generation"] = generation
        context["sources"] = sources_for(generation)
        return context


class MyMaterialsView(LoginRequiredMixin, ListView):
    template_name = "ai/study_list.html"
    paginate_by = 12

    def get_queryset(self):
        return AIGeneration.objects.filter(user=self.request.user)
