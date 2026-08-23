from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.views.generic import CreateView, DetailView, ListView, View

from accounts.permissions import AdminOrTeacherRequiredMixin
from documents.dispatcher import enqueue
from documents.models import ProcessingJob
from library.forms import ResourceForm
from library.models import Resource
from library.services import sanitize_original_filename, user_can_read_resource, visible_resources


def user_can_upload(user):
    return user.is_authenticated and (
        user.is_superuser or user.role in ("TEACHER", "ADMIN")
    )


class ResourceListView(LoginRequiredMixin, ListView):
    template_name = "library/resource_list.html"
    paginate_by = 12

    def get_queryset(self):
        queryset = visible_resources(self.request.user)
        filters = self.request.GET
        query = (filters.get("q") or "").strip()
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(author__icontains=query)
                | Q(description__icontains=query)
            )
        resource_type = filters.get("type") or ""
        if resource_type in Resource.ResourceType.values:
            queryset = queryset.filter(resource_type=resource_type)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["resource_types"] = Resource.ResourceType.choices
        context["current_filters"] = {
            "q": self.request.GET.get("q", ""),
            "type": self.request.GET.get("type", ""),
        }
        context["can_upload"] = user_can_upload(self.request.user)
        return context


class ResourceDetailView(LoginRequiredMixin, DetailView):
    template_name = "library/resource_detail.html"
    slug_field = "public_id"
    slug_url_kwarg = "public_id"

    def get_queryset(self):
        return visible_resources(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        resource = self.object
        if resource.resource_type == Resource.ResourceType.BOOK:
            context["chapters"] = resource.chapters.prefetch_related("sections")
        else:
            context["chapters"] = Resource.chapters.none()
        context["can_upload"] = user_can_upload(self.request.user)
        return context


class _ResourceFileView(LoginRequiredMixin, View):
    """Base for controlled file access; storage paths are never exposed."""

    disposition = "attachment"

    def get_resource(self):
        resource = (
            visible_resources(self.request.user)
            .filter(public_id=self.kwargs["public_id"])
            .first()
        )
        if resource is None or not user_can_read_resource(self.request.user, resource):
            raise Http404("Resource not found.")
        return resource

    def get(self, request, *args, **kwargs):
        resource = self.get_resource()
        if not resource.file:
            raise Http404("Resource has no attached file.")
        response = FileResponse(
            resource.file.open("rb"),
            content_type="application/pdf",
            as_attachment=self.disposition == "attachment",
        )
        filename = (
            sanitize_original_filename(resource.original_filename)
            or f"{resource.public_id}.pdf"
        )
        response["Content-Disposition"] = f'{self.disposition}; filename="{filename}"'
        return response


class ResourceDownloadView(_ResourceFileView):
    disposition = "attachment"


class ResourceReadView(_ResourceFileView):
    """Inline PDF rendering via the browser's native viewer."""

    disposition = "inline"


class ResourceUploadView(AdminOrTeacherRequiredMixin, CreateView):
    model = Resource
    form_class = ResourceForm
    template_name = "library/resource_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        resource = form.save(commit=False)
        resource.uploaded_by = self.request.user
        if self.request.user.is_superuser:
            resource.school = form.cleaned_data["school"]
        else:
            resource.school = self.request.user.school
        resource.store_file(form.cleaned_data["file"])
        resource.processing_status = Resource.ProcessingStatus.UPLOADED
        resource.save()
        # Queue the processing pipeline (runs inline when configured). EXTRACT
        # is enqueued first so workers process it before CHUNK.
        enqueue(resource, ProcessingJob.Step.EXTRACT)
        enqueue(resource, ProcessingJob.Step.CHUNK)
        return redirect(resource.get_absolute_url())