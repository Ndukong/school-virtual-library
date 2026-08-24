from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.generic import CreateView, DetailView, ListView, View

from accounts.permissions import AdminOrTeacherRequiredMixin
from documents.dispatcher import enqueue
from documents.models import ProcessingJob
from library.files import build_file_response, sanitize_original_filename
from library.forms import ResourceForm
from library.models import Resource, ResourceAccessEvent
from library.services import (
    download_exceeded,
    upload_within_quota,
    user_can_read_resource,
    visible_resources,
)


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
            context["chapters"] = resource.chapters.none()
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
        if self.disposition == "attachment":
            exceeded = download_exceeded(request.user)
            if exceeded:
                return HttpResponse(
                    "Download limit reached. Please try again later.",
                    status=429,
                    content_type="text/plain",
                )
        ResourceAccessEvent.objects.create(
            resource=resource,
            user=request.user,
            kind=(
                ResourceAccessEvent.Kind.READ
                if self.disposition == "inline"
                else ResourceAccessEvent.Kind.DOWNLOAD
            ),
        )
        filename = (
            sanitize_original_filename(resource.original_filename)
            or f"{resource.public_id}.pdf"
        )
        return build_file_response(request, resource, self.disposition, filename)


class ResourceDownloadView(_ResourceFileView):
    disposition = "attachment"


class ResourceStreamView(_ResourceFileView):
    """Inline stream used by the watermarked reader; same rules as Read."""

    disposition = "inline"


class ResourceReadView(_ResourceFileView):
    """Read a resource.

    LICENSED/OWNED material is overlayed with a per-user watermark page that
    embeds the stream in a sandboxed iframe; other material streams inline.
    """

    disposition = "inline"

    WATERMARKED_STATUSES = (
        Resource.LicensingStatus.LICENSED,
        Resource.LicensingStatus.OWNED,
    )

    def get(self, request, *args, **kwargs):
        resource = self.get_resource()
        if not resource.file:
            raise Http404("Resource has no attached file.")
        if resource.licensing_status in self.WATERMARKED_STATUSES:
            return render(
                request,
                "library/read_watermark.html",
                {"resource": resource},
            )
        return super().get(request, *args, **kwargs)


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
        uploaded = form.cleaned_data["file"]
        if not upload_within_quota(resource.school, uploaded.size):
            form.add_error("file", "School storage quota reached; ask an administrator.")
            return self.form_invalid(form)
        resource.store_file(uploaded)
        resource.processing_status = Resource.ProcessingStatus.UPLOADED
        resource.save()
        # Queue the processing pipeline (runs inline when configured). EXTRACT
        # is enqueued first so workers process it before CHUNK.
        enqueue(resource, ProcessingJob.Step.EXTRACT)
        enqueue(resource, ProcessingJob.Step.CHUNK)
        return redirect(resource.get_absolute_url())