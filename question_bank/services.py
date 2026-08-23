"""Question bank services: workflow, exam-ready queries, AI import,
duplicate groundwork (AGENTS.md section 15, SKILLS.md sections 10/12)."""

import re

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.permissions import is_admin, is_teacher
from ai.models import AIGeneration
from question_bank.models import Question


class WorkflowError(Exception):
    """Invalid approval-transition or permission problem."""


def _staff_of_school(user, question):
    return user.is_authenticated and (
        user.is_superuser or (
            user.school_id == question.school_id
            and (is_admin(user) or is_teacher(user))
        )
    )


def can_manage(user, question):
    return _staff_of_school(user, question)


def submit_for_review(user, question):
    if not can_manage(user, question):
        raise WorkflowError("You cannot modify this question.")
    if question.approval_status in (
        Question.ApprovalStatus.APPROVED,
        Question.ApprovalStatus.PENDING_REVIEW,
    ):
        raise WorkflowError("Question is already submitted or approved.")
    question.approval_status = Question.ApprovalStatus.PENDING_REVIEW
    question.review_notes = ""
    question.save(update_fields=["approval_status", "review_notes", "updated_at"])
    return question


def approve_question(user, question):
    if not can_manage(user, question):
        raise WorkflowError("You cannot approve this question.")
    if question.approval_status == Question.ApprovalStatus.REJECTED:
        raise WorkflowError("Rejected questions must be edited before approval.")
    question.approval_status = Question.ApprovalStatus.APPROVED
    question.approved_by = user
    question.approved_at = timezone.now()
    question.review_notes = ""
    question.save(update_fields=[
        "approval_status", "approved_by", "approved_at", "review_notes", "updated_at",
    ])
    return question


def reject_question(user, question, notes=""):
    if not can_manage(user, question):
        raise WorkflowError("You cannot reject this question.")
    question.approval_status = Question.ApprovalStatus.REJECTED
    question.approved_by = None
    question.approved_at = None
    question.review_notes = (notes or "").strip()[:2000]
    question.save(update_fields=[
        "approval_status", "approved_by", "approved_at", "review_notes", "updated_at",
    ])
    return question


def questions_for_exam(school, subject=None, topic=None, difficulty=None,
                       bloom_level=None, question_type=None):
    """APPROVED, active, school-scoped questions for the exam generator.

    Phase 8 prefers approved questions before generating new ones; this is
    the single sanctioned source.
    """
    queryset = Question.objects.filter(
        school=school,
        approval_status=Question.ApprovalStatus.APPROVED,
        is_active=True,
    ).select_related("subject", "school_class")
    if subject:
        queryset = queryset.filter(subject=subject)
    if topic:
        queryset = queryset.filter(topic__icontains=topic)
    if difficulty:
        queryset = queryset.filter(difficulty=difficulty)
    if bloom_level:
        queryset = queryset.filter(bloom_level=bloom_level)
    if question_type:
        queryset = queryset.filter(question_type=question_type)
    return queryset


def _normalize_body(text):
    lowered = re.sub(r"\s+", " ", (text or "")).strip().lower()
    return re.sub(r"[^\w\s]", "", lowered)


def find_duplicates(question, exclude_pk=None):
    """Groundwork duplicate detection: normalized exact/prefix matches within
    the same school. Comparison happens in Python because whitespace/punctua-
    tion normalization cannot be expressed as a plain icontains prefilter.
    School-scale volumes keep this cheap; embedding similarity arrives later."""
    body = _normalize_body(question.body)
    if not body:
        return []
    queryset = Question.objects.filter(school_id=question.school_id, is_active=True)
    if exclude_pk:
        queryset = queryset.exclude(pk=exclude_pk)
    prefix = body[:60]
    matches = []
    for candidate in queryset.only("pk", "body")[:1000]:
        candidate_body = _normalize_body(candidate.body)
        if candidate_body == body or candidate_body[:60] == prefix:
            matches.append(candidate)
    return matches


_QA_PATTERN_Q = re.compile(r"^\s*Q\s*[:.)]\s*(.+)$", re.IGNORECASE)
_QA_PATTERN_A = re.compile(r"^\s*A\s*[:.)]\s*(.*)$", re.IGNORECASE)


def parse_practice_questions(text):
    """Parse 'Q: .../A: ...' blocks from AI practice-question output.

    Returns (items, skipped) where items are (question, answer) tuples and
    skipped counts malformed blocks. Never raises on odd formatting.
    """
    items, skipped = [], 0
    current_q, current_a = None, None

    def flush():
        nonlocal current_q, current_a, skipped
        if current_q and current_a:
            items.append((current_q, current_a))
        elif current_q or current_a:
            skipped += 1
        current_q, current_a = None, None

    for raw_line in (text or "").splitlines() + [""]:
        line = raw_line.strip()
        q_match = _QA_PATTERN_Q.match(line)
        a_match = _QA_PATTERN_A.match(line)
        if q_match and not line.upper().lstrip().startswith("A"):
            flush()
            current_q = q_match.group(1).strip()
        elif a_match and current_q is not None:
            current_a = a_match.group(1).strip()
        # All other lines are ignored (headings, numbering noise).
    flush()
    return items, skipped


@transaction.atomic
def import_from_ai_generation(user, generation):
    """Import an AI practice-question generation into the review queue.

    Questions are created PENDING_REVIEW with full traceability to the
    generating AIGeneration; approval remains a human decision.
    """
    if generation.kind != AIGeneration.Kind.PRACTICE_QUESTIONS:
        raise ValueError("Only practice-question generations can be imported.")
    if generation.user_id != user.pk and not user.is_superuser:
        raise WorkflowError("You can only import your own generations.")

    items, skipped = parse_practice_questions(generation.content)
    if not items:
        raise ValidationError(
            f"No importable Q/A pairs found ({skipped} malformed block(s) skipped)."
        )

    source = generation.source_resource
    questions = []
    for body, answer in items:
        questions.append(Question(
            school=user.school,
            subject=source.subject if source else None,
            school_class=source.school_class if source else None,
            topic=generation.topic[:150] or "AI practice",
            question_type=Question.QuestionType.SHORT_STRUCTURED,
            difficulty=Question.Difficulty.MEDIUM,
            marks=1,
            bloom_level=Question.BloomLevel.KNOWLEDGE,
            body=body,
            correct_answer=answer,
            author=user,
            source_resource=source,
            ai_generation=generation,
            approval_status=Question.ApprovalStatus.PENDING_REVIEW,
        ))
    Question.objects.bulk_create(questions)
    return {"imported": len(questions), "skipped": skipped}


def importable_generations(user):
    """The user's practice-question generations, newest first."""
    return AIGeneration.objects.filter(
        user=user, kind=AIGeneration.Kind.PRACTICE_QUESTIONS
    ).select_related("source_resource")