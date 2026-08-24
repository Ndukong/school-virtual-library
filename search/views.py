from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from classes.models import SchoolClass
from library.models import Resource
from search.services import build_snippet, hybrid_search, keyword_search
from subjects.models import Subject


class SearchView(LoginRequiredMixin, TemplateView):
    template_name = "search/results.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request
        query = (request.GET.get("q") or "").strip()
        scope = {
            "subject": request.GET.get("subject") or None,
            "school_class": request.GET.get("class") or None,
            "resource_type": request.GET.get("type") or None,
            "resource": request.GET.get("resource") or None,
            "language": request.GET.get("language") or None,
        }

        user = request.user
        school = user.school
        context.update(
            {
                "query": query,
                "results": [],
                "degraded": False,
                "subjects": Subject.objects.filter(school=school) if school else Subject.objects.none(),
                "classes": SchoolClass.objects.filter(school=school) if school else SchoolClass.objects.none(),
                "resource_types": Resource.ResourceType.choices,
                "current_filters": {k: v for k, v in scope.items() if v},
            }
        )
        if not query:
            return context

        results = hybrid_search(user, query, scope)
        if not results:
            results = keyword_search(user, query, scope)
        for result in results:
            result.snippet = build_snippet(result.chunk, query)
        context["results"] = results
        return context