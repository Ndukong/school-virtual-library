import json
import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from whatsapp.services import (
    HUB_CHALLENGE,
    HUB_MODE,
    HUB_TOKEN,
    WhatsAppError,
    channel_enabled,
    enqueue_inbound,
    normalize_inbound,
    verify_signature,
)

logger = logging.getLogger(__name__)


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
    """Meta webhook entry: verify, persist, return 200 immediately.

    All message handling (linking, routing, replies, pricing) happens in the
    database-backed queue drained by ``process_whatsapp``, so this handler is
    always sub-second and provider retries are cheap to absorb.
    """
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

    if not channel_enabled():
        logger.warning("whatsapp webhook: channel disabled; ignoring payload")
        return HttpResponse("ok")

    for message_id, phone, text in normalize_inbound(payload):
        enqueue_inbound(message_id, phone, text)

    return HttpResponse("ok")