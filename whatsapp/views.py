import hashlib
import hmac
import json
import logging
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models as db_models
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from matches.models import Match, MatchSet

logger = logging.getLogger(__name__)
User = get_user_model()

_SET_RE = re.compile(r'\b(\d{1,2})\s*[-–:]\s*(\d{1,2})(?:\s*[\(\[]\d+[\)\]])?')


def _parse_sets(text):
    """Return list of (a, b) tuples for every NN-NN pattern; None if fewer than 2."""
    raw = _SET_RE.findall(text)
    if len(raw) < 2:
        return None
    return [(int(a), int(b)) for a, b in raw]


def _find_user(phone):
    """Match phone digits to User.phone_number, with or without leading +."""
    return (
        User.objects.filter(phone_number=phone).first()
        or User.objects.filter(phone_number=f"+{phone}").first()
    )


def _process_message(phone, text):
    sets = _parse_sets(text)
    if not sets:
        return

    user = _find_user(phone)
    if not user:
        logger.info("whatsapp: no user for phone %s", phone)
        return

    scheduled = Match.objects.filter(
        status="scheduled",
        season__status="active",
    ).filter(
        db_models.Q(player1=user) | db_models.Q(player2=user)
    )
    count = scheduled.count()
    if count != 1:
        logger.info("whatsapp: %s has %d scheduled matches, skipping", user, count)
        return

    match = scheduled.first()
    is_player1 = match.player1 == user
    opponent = match.player2 if is_player1 else match.player1

    my_sets = sum(1 for a, b in sets if a > b)
    opp_sets = sum(1 for a, b in sets if b > a)
    winner = user if my_sets > opp_sets else opponent

    for i, (my_g, opp_g) in enumerate(sets, 1):
        p1_g = my_g if is_player1 else opp_g
        p2_g = opp_g if is_player1 else my_g
        MatchSet.objects.get_or_create(
            match=match,
            set_number=i,
            defaults={"player1_games": p1_g, "player2_games": p2_g},
        )

    match.status = "pending_confirmation"
    match.winner = winner
    match.entered_by = user
    match.save()

    logger.info(
        "whatsapp: imported match #%d (%s vs %s) sets=%s",
        match.pk, user, opponent, sets,
    )


@csrf_exempt
def webhook(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge", "")
        if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponse(status=403)

    if request.method == "POST":
        sig = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(
            settings.WHATSAPP_APP_SECRET.encode(),
            request.body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            logger.warning("whatsapp: invalid webhook signature")
            return HttpResponse(status=403)

        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return HttpResponse(status=400)

        # Always return 200 to Meta quickly — never let exceptions propagate
        try:
            for entry in payload.get("entry", []):
                for change in entry.get("changes", []):
                    for msg in change.get("value", {}).get("messages", []):
                        if msg.get("type") != "text":
                            continue
                        phone = msg.get("from", "")
                        text = msg.get("text", {}).get("body", "").strip()
                        if phone and text:
                            _process_message(phone, text)
        except Exception:
            logger.exception("whatsapp: error processing webhook payload")

        return HttpResponse(status=200)

    return HttpResponse(status=405)
