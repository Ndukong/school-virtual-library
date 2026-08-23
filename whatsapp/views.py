import json

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from whatsapp.services import (
    HUB_CHALLENGE,
    HUB_MODE,
    HUB_TOKEN,
    RATE_LIMITED_REPLY,
    WhatsAppError,
    get_session,
    handle_text,
    mark_seen,
    normalize_inbound,
    phone_rate_exceeded,
    send_message,
    verify_signature,
)


# Meta signs the raw request body; our middleware chain must not parse it
# before verification, hence csrf_exempt + manual body reads.
@csrf_exempt
@require_GET
def webhook_verify(request):
    if (request.GET.get(HUB_MODE) == "subscribe"
            and request.GET.get(HUB_TOKEN) == settings.WHATSAPP_VERIFY_TOKEN):
        return HttpResponse(request.GET.get(HUB_CHALLENGE, ""))
    return HttpResponseForbidden("Verification failed.")


@csrf_exempt
@require_POST
def webhook_receive(request):
    """Meta webhook entry. Always returns 200 so providers stop retrying."""
    raw = request.body
    try:
        if not verify_signature(raw, request.headers.get("X-Hub-Signature-256")):
            return HttpResponseForbidden("Bad signature.")
    except WhatsAppError:
        return HttpResponseForbidden("Webhook verification unavailable.")

    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError:
        return HttpResponse("ok")  # malformed body: drop, let provider stop retrying

    for message_id, phone, text in normalize_inbound(payload):
        session = get_session(phone)
        if not mark_seen(message_id, phone, session.linked_user, text):
            continue  # provider retried the same wamid

        if phone_rate_exceeded(phone):
            send_message(phone, RATE_LIMITED_REPLY, user=session.linked_user)
            continue

        try:
            replies = handle_text(session, text)
        except Exception as exc:  # noqa: BLE001 - channel must survive
            replies = [f"Something went wrong processing your message: {exc}"]
        for reply in replies:
            if reply:
                send_message(phone, reply, user=session.linked_user)

    return HttpResponse("ok")