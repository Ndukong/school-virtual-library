"""JSON API v1 (WP11).

A thin adapter over the existing services, with the same security rules as
the web: library lists start from visible_resources() (permission filtering
BEFORE retrieval), search goes through search.services, the AI ask path uses
ai.rag.ask (rate limited, budget metered), and answers are owner-or-404.
Business logic lives in the services; this layer only marshals JSON.

Auth: session-based (the PWA and any first-party client), like the web.
Unauthenticated requests get a JSON 401, never a redirect. Cross-school and
cross-user targets 404 exactly like the web views.
"""

import json

from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views import View

from accounts.permissions import is_student, is_teacher
from ai.models import AIInteraction
from ai.providers.base import AIError
from ai.rag import ask, sources_for
from ai.ratelimit import RateLimited
from library.models import Resource
from library.services import (
    language_code,
    language_search_values,
    visible_resources,
)
from question_bank.models import Question
from search.services import build_snippet, hybrid_search, keyword_search

_PAGE_SIZE = 20


class JsonLoginRequiredMixin:
    """LoginRequiredMixin that answers 401 instead of redirecting to /login/."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required."}, status=401)
        return super().dispatch(request, *args, **kwargs)


class _Paginator:
    def __init__(self, request):
        try:
            self.size = max(1, min(int(request.GET.get("page_size", _PAGE_SIZE)), 50))
        except (TypeError, ValueError):
            self.size = _PAGE_SIZE
        try:
            self.page = max(1, int(request.GET.get("page", 1)))
        except (TypeError, ValueError):
            self.page = 1

    def slice(self, queryset):
        start = (self.page - 1) * self.size
        return list(queryset[start : start + self.size])

    def meta(self, count):
        return {
            "count": count,
            "page": self.page,
            "page_size": self.size,
            "next": count > self.page * self.size,
            "previous": self.page > 1,
        }


def _absolute_url(request, path):
    return request.build_absolute_uri(path)


class ResourceListApiView(JsonLoginRequiredMixin, View):
    def get(self, request):
        queryset = visible_resources(request.user)
        query = (request.GET.get("q") or "").strip()
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(author__icontains=query)
                | Q(description__icontains=query)
            )
        resource_type = request.GET.get("type") or ""
        if resource_type in Resource.ResourceType.values:
            queryset = queryset.filter(resource_type=resource_type)
        language = language_code(request.GET.get("language") or "")
        if language:
            queryset = queryset.filter(language__in=language_search_values(language))

        queryset = queryset.order_by("-created_at")
        count = queryset.count()
        page = _Paginator(request).slice(queryset)
        return JsonResponse({
            **_Paginator(request).meta(count),
            "results": [
                {
                    "public_id": str(item.public_id),
                    "title": item.title,
                    "resource_type": item.resource_type,
                    "language": item.language,
                    "subject": item.subject.name if item.subject else None,
                    "author": item.author,
                    "school": item.school.name,
                    "processing_status": item.processing_status,
                    "url": _absolute_url(
                        request, reverse("library-detail", args=[item.public_id])
                    ),
                }
                for item in page
            ],
        })


class SearchApiView(JsonLoginRequiredMixin, View):
    def get(self, request):
        query = (request.GET.get("q") or "").strip()
        if len(query) < 2:
            return JsonResponse({"error": "q must be at least 2 characters."}, status=400)

        scope = {
            "subject": request.GET.get("subject") or None,
            "school_class": request.GET.get("class") or None,
            "resource_type": request.GET.get("type") or None,
            "language": language_code(request.GET.get("language") or ""),
        }
        results = hybrid_search(request.user, query, scope)
        if not results:
            results = keyword_search(request.user, query, scope)

        payload = []
        for result in results:
            chunk = result.chunk
            resource = chunk.resource
            payload.append({
                "resource_public_id": str(resource.public_id),
                "title": resource.title,
                "author": resource.author,
                "subject": resource.subject.name if resource.subject else None,
                "page": chunk.page_start,
                "semantic_score": result.semantic_score,
                "snippet": build_snippet(chunk, query),
                "url": _absolute_url(
                    request, reverse("library-detail", args=[resource.public_id])
                ),
            })
        return JsonResponse({"query": query, "count": len(payload), "results": payload})


class AskApiView(JsonLoginRequiredMixin, View):
    _ALLOWED_SCOPES = AIInteraction.Scope.values

    def _body(self, request):
        if request.content_type == "application/json":
            try:
                return json.loads(request.body or b"{}")
            except (ValueError, UnicodeDecodeError):
                return {}
        return request.POST

    def post(self, request):
        data = self._body(request)
        question = (data.get("question") or "").strip()
        if not question:
            return JsonResponse({"error": str(_("Please enter a question."))}, status=400)

        scope = (data.get("scope") or AIInteraction.Scope.LIBRARY).upper()
        if scope not in self._ALLOWED_SCOPES:
            return JsonResponse({"error": f"Unknown scope: {scope}"}, status=400)
        book = (data.get("book") or "").strip() or None
        chapter = (data.get("chapter") or "").strip() or None

        try:
            interaction = ask(
                request.user,
                question,
                scope=scope,
                resource_public_id=book,
                chapter_id=chapter,
            )
        except RateLimited as exc:
            return JsonResponse({"error": str(exc)}, status=429)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except AIError:
            return JsonResponse(
                {"error": "The AI service could not complete the request."}, status=503
            )

        sources = []
        for chunk in sources_for(interaction):
            sources.append({
                "resource_public_id": str(chunk.resource.public_id),
                "title": chunk.resource.title,
                "page": chunk.page_start,
                "chapter": chunk.chapter.title if chunk.chapter else None,
                "section": chunk.section.title if chunk.section else None,
            })
        return JsonResponse({
            "public_id": str(interaction.public_id),
            "scope": interaction.scope,
            "question": interaction.question,
            "answer": interaction.answer,
            "used_provider": interaction.used_provider,
            "prompt_version": interaction.prompt_version,
            "model": interaction.model,
            "sources": sources,
            "answer_url": _absolute_url(
                request, reverse("api-answer", args=[interaction.public_id])
            ),
        })


class AnswerApiView(JsonLoginRequiredMixin, View):
    def get(self, request, public_id):
        interaction = AIInteraction.objects.filter(public_id=public_id).first()
        if interaction is None or (
            interaction.user_id != request.user.pk and not request.user.is_superuser
        ):
            return JsonResponse({"error": "Answer not found."}, status=404)
        sources = []
        for chunk in sources_for(interaction):
            sources.append({
                "resource_public_id": str(chunk.resource.public_id),
                "title": chunk.resource.title,
                "page": chunk.page_start,
            })
        return JsonResponse({
            "public_id": str(interaction.public_id),
            "scope": interaction.scope,
            "question": interaction.question,
            "answer": interaction.answer,
            "used_provider": interaction.used_provider,
            "sources": sources,
        })


class QuestionListApiView(JsonLoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        if user.school_id is None:
            return JsonResponse({"error": "Not permitted."}, status=403)
        queryset = Question.objects.filter(school_id=user.school_id).select_related(
            "subject"
        )

        if is_student(user):
            acknowledged_states = [Question.ApprovalStatus.APPROVED]
        elif is_teacher(user) or user.is_superuser:
            acknowledged_states = (
                Question.ApprovalStatus.values
                if user.is_superuser
                else [
                    Question.ApprovalStatus.APPROVED,
                    Question.ApprovalStatus.PENDING_REVIEW,
                ]
            )
        else:
            return JsonResponse({"error": "Not permitted."}, status=403)
        queryset = queryset.filter(approval_status__in=acknowledged_states)

        subject = request.GET.get("subject") or None
        if subject:
            queryset = queryset.filter(subject_id=subject)
        language = language_code(request.GET.get("language") or "")
        if language:
            queryset = queryset.filter(language=language)

        queryset = queryset.order_by("-created_at")
        count = queryset.count()
        page = _Paginator(request).slice(queryset)
        return JsonResponse({
            **_Paginator(request).meta(count),
            "results": [
                {
                    "public_id": str(item.public_id),
                    "subject": item.subject.name if item.subject else None,
                    "topic": item.topic,
                    "question_type": item.question_type,
                    "language": item.language,
                    "marks": item.marks,
                    "approval_status": item.approval_status,
                    "body": item.body,
                    "options": item.options,
                }
                for item in page
            ],
        })