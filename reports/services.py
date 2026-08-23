"""School-level analytics (Phase 12).

ALL results are aggregates. Individual students are never named or exposed;
practice statistics roll up across students per class/subject/topic only
(AGENTS.md sections 18/22). Everything is scoped to one school - superusers
select the school explicitly.
"""

from django.db.models import Count, Sum

from accounts.models import User
from ai.models import AIGeneration, AIInteraction
from learning.models import AttemptResponse, PracticeAttempt
from library.models import Resource, ResourceAccessEvent

WEEK_DAYS = 14


def _month_start():
    from django.utils import timezone

    now = timezone.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def library_stats(school):
    resources = Resource.objects.filter(school=school)
    access = ResourceAccessEvent.objects.filter(resource__school=school)
    month = _month_start()
    return {
        "total_resources": resources.count(),
        "active_resources": resources.filter(is_active=True).count(),
        "by_type": list(
            resources.values("resource_type").annotate(count=Count("pk")).order_by("-count")
        ),
        "processing_ready": resources.filter(
            processing_status=Resource.ProcessingStatus.READY
        ).count(),
        "processing_failed": resources.filter(
            processing_status=Resource.ProcessingStatus.FAILED
        ).count(),
        "uploads_this_month": resources.filter(created_at__gte=month).count(),
        "access_total": access.count(),
        "access_this_month": access.filter(created_at__gte=month).count(),
        "top_subjects": list(
            resources.filter(subject__isnull=False)
            .values("subject__name")
            .annotate(count=Count("pk"))
            .order_by("-count")[:5]
        ),
    }


def ai_stats(school):
    interactions = AIInteraction.objects.filter(school=school)
    generations = AIGeneration.objects.filter(school=school)
    return {
        "interaction_total": interactions.count(),
        "generation_total": generations.count(),
        "interaction_failures": interactions.filter(used_provider=False).count(),
        "generation_failures": generations.filter(used_provider=False).count(),
        "by_scope": list(
            interactions.values("scope").annotate(count=Count("pk")).order_by("-count")
        ),
        "by_generation_kind": list(
            generations.values("kind").annotate(count=Count("pk")).order_by("-count")
        ),
        "models_used": list(
            interactions.exclude(model="")
            .values("model").annotate(count=Count("pk")).order_by("-count")[:6]
        ),
        "recent_days": list(
            interactions.values("created_at__date")
            .annotate(count=Count("pk"))
            .order_by("-created_at__date")[:WEEK_DAYS]
        ),
    }


def practice_stats(school):
    attempts = PracticeAttempt.objects.filter(
        school=school, status=PracticeAttempt.Status.SUBMITTED
    )
    aggregated = attempts.aggregate(
        total=Count("pk"),
        earned=Sum("earned_marks"),
        possible=Sum("possible_marks"),
    )
    possible = aggregated["possible"] or 0
    earned = aggregated["earned"] or 0

    by_subject = list(
        attempts.filter(subject__isnull=False)
        .values("subject__name")
        .annotate(count=Count("pk"))
        .order_by("-count")
    )
    by_class = list(
        attempts.filter(student__student_profile__school_class__isnull=False)
        .values("student__student_profile__school_class__name")
        .annotate(count=Count("pk"))
        .order_by("student__student_profile__school_class__name")
    )
    return {
        "submitted_count": aggregated["total"] or 0,
        "average_percent": round(earned * 100.0 / possible, 1) if possible else 0.0,
        "by_subject": by_subject,
        "by_class": by_class,
        "self_marked_count": AttemptResponse.objects.filter(
            attempt__school=school, self_marked=True
        ).count(),
    }


def popular_topics(school):
    """Practiced topics with aggregate accuracy - never per-student."""
    topics = (
        AttemptResponse.objects.filter(
            attempt__school=school,
            attempt__status=PracticeAttempt.Status.SUBMITTED,
            is_correct__isnull=False,
        )
        .values("question__topic")
        .annotate(attempted=Count("pk"))
        .order_by("-attempted")[:10]
    )
    rows = []
    for row in topics:
        count = row["attempted"]
        correct = AttemptResponse.objects.filter(
            attempt__school=school,
            attempt__status=PracticeAttempt.Status.SUBMITTED,
            question__topic=row["question__topic"],
            is_correct=True,
        ).count()
        rows.append({
            "topic": row["question__topic"],
            "attempted": count,
            "accuracy": round(correct * 100.0 / count, 1) if count else 0.0,
        })
    rows.sort(key=lambda r: (-r["attempted"], r["accuracy"]))
    return rows


def teacher_activity(school):
    teachers = (
        User.objects.filter(school=school, role__in=("TEACHER", "ADMIN"))
        .annotate(
            uploads=Count("uploaded_resources", distinct=True),
            questions=Count("authored_questions", distinct=True),
            exams=Count("created_exams", distinct=True),
            ai_pieces=Count("ai_generations", distinct=True),
        )
        .order_by("username")
    )
    return [
        {
            "username": row.username,
            "role": row.get_role_display(),
            "uploads": row.uploads,
            "questions": row.questions,
            "exams": row.exams,
            "ai_pieces": row.ai_pieces,
        }
        for row in teachers
    ]