"""WhatsApp channel services (AGENTS.md section 19, SKILLS.md section 20).

Everything here is plumbing; handlers call the existing business services
(search, RAG, practice) rather than duplicating logic. WhatsApp never becomes
a second database.
"""

import hashlib
import hmac
import json
import secrets
import time
import urllib.request
import uuid

from django.conf import settings
from django.utils import timezone

from learning.models import PracticeAttempt
from learning.services import progress_summary, start_quiz, submit_attempt
from whatsapp.models import WhatsAppLink, WhatsAppMessage, WhatsAppSession

# Meta's webhook verification fields.
HUB_MODE = "hub.mode"
HUB_TOKEN = "hub.verify_token"
HUB_CHALLENGE = "hub.challenge"


class WhatsAppError(Exception):
    """Channel-level failure (signature, configuration, provider)."""


# ---------------------------------------------------------------------------
# Verification and normalization
# ---------------------------------------------------------------------------

def verify_signature(payload_bytes, signature_header):
    """Constant-time check of X-Hub-Signature-256. Returns bool.

    Raises WhatsAppError when verification is required but the header is
    missing/malformed, or the app secret is unset outside DEBUG (fail-closed).
    """
    secret = getattr(settings, "WHATSAPP_APP_SECRET", "")
    if not secret:
        if getattr(settings, "DEBUG", False):
            return True  # dev/testing convenience; never in production
        raise WhatsAppError("WHATSAPP_APP_SECRET is not configured.")
    if not signature_header:
        raise WhatsAppError("Missing X-Hub-Signature-256 header.")
    expected = "sha256=" + hmac.new(
        secret.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def verify_token_supplied():
    """True when the webhook can perform the GET verification handshake."""
    return bool(getattr(settings, "WHATSAPP_VERIFY_TOKEN", ""))


def normalize_inbound(payload):
    """Yield (message_id, phone_number, body) for TEXT messages only."""
    for entry in (payload or {}).get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                mid = message.get("id", "")
                phone = (message.get("from") or "").strip()
                if message.get("type") != "text":
                    continue  # media/audio/etc. are unsupported gracefully
                text = ((message.get("text") or {}).get("body") or "").strip()
                if mid and phone:
                    yield mid, f"+{phone.lstrip('+')}", text


def mark_seen(message_id, phone_number, user, body=""):
    """Record inbound message; returns True on first sight of this wamid."""
    _, created = WhatsAppMessage.objects.get_or_create(
        message_id=message_id,
        defaults={
            "phone_number": phone_number,
            "user": user,
            "direction": "IN",
            "body": body[:5000],
        },
    )
    return created


# ---------------------------------------------------------------------------
# Phone rate limiting (independent of AI per-user limits)
# ---------------------------------------------------------------------------

def phone_rate_exceeded(phone_number):
    limit = getattr(settings, "WHATSAPP_RATE_LIMIT_PER_MINUTE", 10)
    since = timezone.now() - timezone.timedelta(minutes=1)
    count = WhatsAppMessage.objects.filter(
        phone_number=phone_number,
        direction="IN",
        created_at__gte=since,
    ).count()
    return count >= limit


# ---------------------------------------------------------------------------
# Session + linking (phone numbers are never trusted on their own)
# ---------------------------------------------------------------------------

def get_session(phone_number):
    session, _ = WhatsAppSession.objects.get_or_create(phone_number=phone_number)
    return session


def create_link_code(user, minutes=None):
    minutes = minutes or getattr(settings, "WHATSAPP_LINK_CODE_MINUTES", 15)
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    code = (user.username[:4].upper() + secrets.choice(alphabet) +
            secrets.choice(alphabet))
    return WhatsAppLink.objects.create(
        user=user,
        code=code,
        expires_at=timezone.now() + timezone.timedelta(minutes=minutes),
    )


def link_phone(session, code):
    """Bind a phone number to the user owning an unused, unexpired code."""
    code = (code or "").strip().upper()
    link = WhatsAppLink.objects.select_related("user").filter(code=code).first()
    if link is None or not link.is_valid():
        return None, (
            "That link code is invalid or has expired. Ask your school "
            "administrator for a fresh code, or generate one on your dashboard."
        )
    link.used_at = timezone.now()
    link.save(update_fields=["used_at"])
    session.linked_user = link.user
    session.state = "MENU"
    session.context = {}
    session.save(update_fields=["linked_user", "state", "context", "last_seen_at"])
    return link.user, None


# ---------------------------------------------------------------------------
# Outbound sending
# ---------------------------------------------------------------------------

def send_message(phone_number, text, user=None):
    """Send one outbound text; always logged regardless of provider."""
    body = text.strip()[:5000]
    if getattr(settings, "WHATSAPP_PROVIDER", "console") == "meta":
        _meta_send(phone_number, body)
    else:
        print(f"[whatsapp console] -> {phone_number}: {body[:80]}")
    WhatsAppMessage.objects.create(
        message_id=f"out-{uuid.uuid4().hex}",
        phone_number=phone_number,
        user=user,
        direction="OUT",
        body=body,
    )
    return body


def _meta_send(phone_number, body):
    token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
    phone_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
    version = getattr(settings, "WHATSAPP_API_VERSION", "v21.0")
    if not token or not phone_id:
        raise WhatsAppError("WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID not configured.")
    url = f"https://graph.facebook.com/{version}/{phone_id}/messages"
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": body},
    }).encode()
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    timeout = getattr(settings, "AI_TIMEOUT_SECONDS", 30)
    last_error = ""
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                json.loads(response.read().decode("utf-8"))
            return
        except Exception as exc:  # noqa: BLE001 - network layer
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt == 0:
                time.sleep(1)
    raise WhatsAppError(f"Outbound WhatsApp send failed: {last_error}")


# ---------------------------------------------------------------------------
# Menu router (thin; delegates business logic to existing services)
# ---------------------------------------------------------------------------

FALLBACK_UNLINKED = (
    "I don't know who you are yet. Link your phone by replying:\n"
    "LINK <code>\n\nA code protects your account - it is generated in your "
    "school dashboard (or by your administrator) and expires in about 15 "
    "minutes. MENU shows the full command list."
)

HELP_MENU = (
    "School Virtual Library on WhatsApp.\n"
    "Commands:\n"
    "• LINK <code> - connect your phone to your account\n"
    "• SEARCH <query> - find material in your library\n"
    "• ASK <question> - ask the AI Librarian (grounded)\n"
    "• QUIZ - start a 3-question objective quiz\n"
    "• PROGRESS - your practice summary\n"
    "• MENU - show this message again\n"
    "• STOP - unlink this phone"
)

RATE_LIMITED_REPLY = (
    "You are sending messages too quickly. Please wait a minute and try again."
)

_UNKNOWN_REPLY = "I didn't understand that. Type MENU for the command list."


def _link_error(code, session):
    _, error = link_phone(session, code)
    return error or "Connected."


def handle_text(session, text):
    """Return reply strings. Business logic lives in existing services."""
    upper = (text or "").strip().upper()

    if not session.linked():
        if upper.startswith("LINK"):
            tokens = upper.split()
            code = tokens[1] if len(tokens) > 1 else ""
            return [_link_reply(session, code)]
        return [FALLBACK_UNLINKED]

    if upper == "STOP":
        session.linked_user = None
        session.state = "MENU"
        session.context = {}
        session.save(update_fields=["linked_user", "state", "context", "last_seen_at"])
        return ["Your phone is unlinked. LINK <code> anytime to reconnect."]

    if upper in ("HELP", "MENU"):
        return [HELP_MENU]

    if session.state == "QUIZ" and session.context.get("quiz"):
        return _handle_quiz_answer(session, text)

    if upper.startswith("LINK"):
        tokens = upper.split()
        return [_link_reply(session, tokens[1] if len(tokens) > 1 else "")]

    if upper.startswith("SEARCH"):
        return [_search_reply(session.linked_user, text[len("SEARCH"):].strip())]

    if upper.startswith("ASK"):
        return [_ask_reply(session.linked_user, text[len("ASK"):].strip())]

    if upper.startswith("QUIZ"):
        return _quiz_reply(session, text[len("QUIZ"):].strip())

    if upper == "PROGRESS":
        return [_progress_reply(session.linked_user)]

    return [_UNKNOWN_REPLY]


def _link_reply(session, code):
    user, error = link_phone(session, code)
    if error:
        return error
    return f"Linked to {user.get_full_name() or user.username}, {user.get_role_display()}."


def _search_reply(user, query):
    from search.services import keyword_search

    if not query:
        return "SEARCH <topic> - for example: SEARCH electromagnetic induction"
    results = keyword_search(user, query, limit=3)
    if not results:
        return "No results in your library for that. Try different words."
    lines = [f"You have {len(results)} result(s):"]
    for result in results:
        chapter = result.chunk.chapter.title if result.chunk.chapter else None
        suffix = f" (ch. {chapter})" if chapter else ""
        lines.append(f"• {result.resource.title}{suffix}")
    return "\n".join(lines)


def _ask_reply(user, question):
    from ai.models import AIInteraction
    from ai.providers import AIError
    from ai.rag import ask
    from ai.ratelimit import RateLimited

    if not question:
        return "ASK <question> - for example: ASK what is electromagnetic induction?"
    try:
        interaction = ask(user, question, scope=AIInteraction.Scope.LIBRARY)
    except AIError:
        return "The AI service is temporarily unavailable; please try again shortly."
    except RateLimited as exc:
        return str(exc)
    answer = interaction.answer
    if len(answer) > 1200:
        answer = answer[:1200] + "… (open the full answer on the web portal)"
    return answer


def _quiz_reply(session, size_text):
    size = 3
    try:
        size = min(max(int(size_text.strip()), 1), 3)
    except (ValueError, AttributeError):
        pass
    try:
        attempt = start_quiz(session.linked_user, objective_only=True, size=size)
    except Exception as exc:  # noqa: BLE001 - friendly channel error
        return [f"Could not start a quiz: {exc}. Approve practice questions in "
                "the Question Bank first."]
    session.state = "QUIZ"
    session.context = {
        "quiz": {"attempt": str(attempt.public_id), "answers": {}, "position": 0}
    }
    session.save(update_fields=["state", "context", "last_seen_at"])
    responses = list(attempt.responses.select_related("question").order_by("position"))
    if not responses:
        return ["No quiz questions could be prepared."]
    return ["Quiz time! Reply the option text for each question.\n\n" +
            _render_question(responses[0], 1)]


def _render_question(response, number):
    question = response.question
    if question.options:
        options = "\n".join(f"• {option}" for option in question.options)
        return f"Q{number} [{question.marks} marks]\n{question.body}\n{options}"
    return f"Q{number} [{question.marks} marks]\n{question.body}"


def _handle_quiz_answer(session, text):
    quiz = session.context["quiz"]
    try:
        attempt = PracticeAttempt.objects.get(public_id=quiz["attempt"])
    except PracticeAttempt.DoesNotExist:
        session.state = "MENU"
        session.context = {}
        session.save(update_fields=["state", "context", "last_seen_at"])
        return ["Your quiz ended unexpectedly. Type QUIZ to start a new one."]

    responses = list(attempt.responses.select_related("question").order_by("position"))
    position = quiz["position"]
    current = responses[position]
    quiz["answers"][str(current.pk)] = text
    position += 1
    quiz["position"] = position
    session.save(update_fields=["context", "last_seen_at"])
    if position >= len(responses):
        return _finish_quiz(session, attempt)
    return [_render_question(responses[position], position + 1)]


def _finish_quiz(session, attempt):
    quiz = session.context["quiz"]
    try:
        submit_attempt(attempt, quiz["answers"])
    except Exception as exc:  # noqa: BLE001 - surface friendly grade error
        return [f"Could not grade quiz: {exc}"]
    session.state = "MENU"
    session.context = {}
    session.save(update_fields=["state", "context", "last_seen_at"])
    return [
        f"Quiz complete: {attempt.earned_marks}/{attempt.possible_marks} "
        f"({attempt.score_percent}%). See explanations on the web portal.",
    ]


def _progress_reply(user):
    summary = progress_summary(user)
    if not summary["submitted_count"]:
        return "You have not submitted any practice yet. Try: QUIZ"
    lines = [f"You have completed {summary['submitted_count']} quiz(es)."]
    for subject, entry in summary["per_subject"].items():
        lines.append(f"• {subject}: {entry['average']}% avg over {entry['attempts']}")
    return "\n".join(lines)