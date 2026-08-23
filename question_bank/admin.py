from django.contrib import admin

from common.admin import SchoolScopedModelAdmin
from question_bank.models import Question
from question_bank.services import approve_question, reject_question


@admin.action(description="Approve selected questions")
def approve_selected(modeladmin, request, queryset):
    for question in queryset:
        try:
            approve_question(request.user, question)
        except Exception:  # noqa: BLE001 - one bad row must not abort the batch
            pass


@admin.action(description="Reject selected questions")
def reject_selected(modeladmin, request, queryset):
    for question in queryset:
        try:
            reject_question(request.user, question, "Rejected via admin bulk action.")
        except Exception:  # noqa: BLE001
            pass


@admin.register(Question)
class QuestionAdmin(SchoolScopedModelAdmin):
    list_display = (
        "body", "question_type", "marks", "bloom_level", "difficulty",
        "subject", "school", "approval_status", "author",
    )
    list_filter = (
        "school", "approval_status", "question_type", "difficulty",
        "bloom_level", "subject",
    )
    search_fields = ("body", "topic", "subtopic", "correct_answer")
    readonly_fields = ("public_id", "approved_by", "approved_at", "created_at", "updated_at")
    actions = [approve_selected, reject_selected]