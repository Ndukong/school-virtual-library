"""Practice services: quiz creation, grading, self-marking, private progress.

Privacy rules (AGENTS.md sections 18/22): attempts are visible only to the
owning student; progress aggregates never cross students.
"""

import random
import re

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils.translation import gettext as _

from examinations.models import Exam
from learning.models import AttemptResponse, PracticeAttempt
from question_bank.models import Question


class PracticeError(Exception):
    """User-facing practice failure."""


OBJECTIVE_TYPES = {
    Question.QuestionType.MCQ,
    Question.QuestionType.TRUE_FALSE,
}


def _normalize(text):
    lowered = re.sub(r"\s+", " ", (text or "")).strip().lower()
    return re.sub(r"[^\w\s]", "", lowered)


def student_class_id(student):
    """Resolve the class from the student's profile (not the auth user)."""
    profile = getattr(student, "student_profile", None)
    return profile.school_class_id if profile else None


def get_owned_attempt(user, public_id):
    """Strict ownership: anyone other than the student gets 404-equivalent."""
    try:
        attempt = PracticeAttempt.objects.select_related(
            "student", "subject", "exam"
        ).get(public_id=public_id)
    except PracticeAttempt.DoesNotExist:
        raise PermissionDenied(_("Attempt not found.")) from None
    if attempt.student_id != user.pk:
        raise PermissionDenied(_("Attempt not found."))
    return attempt


@transaction.atomic
def start_quiz(student, subject=None, topic="", size=None, objective_only=False,
               language=None):
    """Draw a random approved quiz for the student's school (+ their class)."""
    size = int(size or getattr(settings, "PRACTICE_DEFAULT_SIZE", 5))
    max_size = getattr(settings, "PRACTICE_MAX_SIZE", 20)
    size = max(1, min(size, max_size))

    queryset = Question.objects.filter(
        school=student.school,
        approval_status=Question.ApprovalStatus.APPROVED,
        is_active=True,
    )
    if language:
        queryset = queryset.filter(language=language)
    if objective_only:
        queryset = queryset.filter(question_type__in=OBJECTIVE_TYPES)
    if subject:
        queryset = queryset.filter(subject=subject)
    class_id = student_class_id(student)
    if class_id:
        queryset = queryset.filter(
            models_school_class_or_null(class_id)
        )
    if topic.strip():
        queryset = queryset.filter(topic__icontains=topic.strip())

    pool = list(queryset.select_related("subject"))
    if not pool:
        raise PracticeError(
            _("No approved questions are available for that filter yet. "
              "Try a different subject/topic.")
        )
    random.shuffle(pool)
    selected = pool[:size]

    attempt = PracticeAttempt.objects.create(
        student=student,
        school=student.school,
        subject=selected[0].subject,
        source_type=PracticeAttempt.Source.SELF_QUIZ,
        topic_filter=topic.strip()[:200],
        possible_marks=sum(q.marks for q in selected),
    )
    AttemptResponse.objects.bulk_create([
        AttemptResponse(attempt=attempt, question=q, position=index)
        for index, q in enumerate(selected, start=1)
    ])
    return attempt


def models_school_class_or_null(school_class):
    from django.db.models import Q

    return Q(school_class=school_class) | Q(school_class__isnull=True)


@transaction.atomic
def start_from_exam(student, exam):
    """Practice a PUBLISHED exam from the student's school/class."""
    if exam.school_id != student.school_id:
        raise PracticeError(_("That exam is not available for your school."))
    if exam.status != Exam.Status.PUBLISHED:
        raise PracticeError(_("Only published exams can be practiced."))
    if exam.school_class_id and student_class_id(student) != exam.school_class_id:
        raise PracticeError(_("That exam is set for a different class."))

    slots = list(exam.exam_questions.select_related("question").order_by("position"))
    if not slots:
        raise PracticeError(_("That exam has no questions."))

    attempt = PracticeAttempt.objects.create(
        student=student,
        school=student.school,
        subject=exam.subject,
        source_type=PracticeAttempt.Source.PUBLISHED_EXAM,
        exam=exam,
        topic_filter=f"Exam: {exam.title}"[:200],
        possible_marks=sum(slot.marks for slot in slots),
    )
    AttemptResponse.objects.bulk_create([
        AttemptResponse(attempt=attempt, question=slot.question,
                        position=slot.position)
        for slot in slots
    ])
    return attempt


def _grade_objective(response, given_answer):
    question = response.question
    correct = _normalize(question.correct_answer) == _normalize(given_answer)
    response.is_correct = correct
    response.awarded_marks = question.marks if correct else 0


@transaction.atomic
def submit_attempt(attempt, answers):
    """Grade and close an attempt. answers: {response_pk: given_text}."""
    if attempt.status == PracticeAttempt.Status.SUBMITTED:
        raise PracticeError(_("This attempt was already submitted."))
    earned = 0
    for response in attempt.responses.select_related("question"):
        given = (answers.get(str(response.pk)) or "").strip()
        response.given_answer = given[:5000]
        if response.question.question_type in OBJECTIVE_TYPES:
            _grade_objective(response, given)
            earned += response.awarded_marks
        else:
            # Structured/essay types await teacher-scheme self-review.
            response.is_correct = None
            response.awarded_marks = 0
        response.save(update_fields=[
            "given_answer", "is_correct", "awarded_marks", "updated_at",
        ])
    attempt.earned_marks = earned
    attempt.status = PracticeAttempt.Status.SUBMITTED
    attempt.save(update_fields=["earned_marks", "status", "updated_at"])
    return attempt


@transaction.atomic
def record_self_mark(user, response, is_correct):
    """Student applies the teacher's marking scheme to an ungraded response."""
    attempt = response.attempt
    if attempt.student_id != user.pk:
        raise PermissionDenied(_("Not your attempt."))
    if attempt.status != PracticeAttempt.Status.SUBMITTED:
        raise PracticeError(_("Submit the attempt before self-marking."))
    if response.question.question_type in OBJECTIVE_TYPES:
        raise PracticeError(_("Objective questions are graded automatically."))
    if response.is_correct is not None:
        raise PracticeError(_("Already marked."))

    previous = response.awarded_marks
    response.is_correct = bool(is_correct)
    response.self_marked = True
    response.awarded_marks = response.question.marks if is_correct else 0
    response.save(update_fields=["is_correct", "self_marked", "awarded_marks", "updated_at"])
    attempt.earned_marks = attempt.earned_marks - previous + response.awarded_marks
    attempt.save(update_fields=["earned_marks", "updated_at"])
    return response


def progress_summary(student):
    """Private aggregate over the student's own submitted attempts."""
    submitted = PracticeAttempt.objects.filter(
        student=student, status=PracticeAttempt.Status.SUBMITTED
    ).select_related("subject")
    total = submitted.count()
    per_subject = {}
    recent = []
    for attempt in submitted[:50]:
        percent = attempt.score_percent
        key = attempt.subject.name if attempt.subject else "General"
        entry = per_subject.setdefault(key, {"attempts": 0, "average": 0.0})
        entry["attempts"] += 1
        entry["average"] = round(
            (entry["average"] * (entry["attempts"] - 1) + percent) / entry["attempts"], 1
        )
        recent.append({
            "attempt": attempt,
            "percent": percent,
        })
    return {
        "submitted_count": total,
        "per_subject": per_subject,
        "recent": recent,
    }


def recommend_topics(student, limit=3):
    """Weakest topics by accuracy across the student's own graded responses."""
    responses = AttemptResponse.objects.filter(
        attempt__student=student,
        attempt__status=PracticeAttempt.Status.SUBMITTED,
        is_correct__isnull=False,
    ).select_related("question")
    stats = {}
    for response in responses:
        topic = response.question.topic
        entry = stats.setdefault(topic, {"correct": 0, "total": 0})
        entry["total"] += 1
        if response.is_correct:
            entry["correct"] += 1
    ranked = sorted(
        stats.items(),
        key=lambda pair: (pair[1]["correct"] / pair[1]["total"], -pair[1]["total"]),
    )
    recommendations = []
    for topic, entry in ranked[:limit]:
        percent = round(entry["correct"] * 100.0 / entry["total"], 1) if entry["total"] else 0.0
        recommendations.append({"topic": topic, "accuracy": percent, "total": entry["total"]})
    return recommendations