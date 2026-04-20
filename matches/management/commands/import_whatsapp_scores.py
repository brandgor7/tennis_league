"""
Management command: import match scores from a WhatsApp group via Green API.

Setup:
  1. Sign up at https://green-api.com (free tier — 1 instance, no expiry)
  2. Create an instance and scan the QR code with your WhatsApp
  3. Note your Instance ID and API token
  4. Find your group's chat ID (Settings > Notifications in Green API, or use the
     getContacts endpoint) — format: 120363xxxxxxxxxx@g.us
  5. Set the three env vars below in .env

Usage:
  python manage.py import_whatsapp_scores
  python manage.py import_whatsapp_scores --hours 48
  python manage.py import_whatsapp_scores --dry-run
"""

import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import models as db_models

from matches.models import Match, MatchSet

User = get_user_model()

# Matches patterns like: 6-4, 7-5, 7-6, 10-7, 6-4(4), 6-4 (4)
_SET_RE = re.compile(r'\b(\d{1,2})\s*[-–:]\s*(\d{1,2})(?:\s*[\(\[]\d+[\)\]])?')


def _parse_sets(text):
    """
    Return list of (a, b) int tuples for every NN-NN pattern in text.
    Returns None if fewer than 2 set-like scores are found.
    """
    raw = _SET_RE.findall(text)
    if len(raw) < 2:
        return None
    return [(int(a), int(b)) for a, b in raw]


def _fetch_group_messages(instance_id, api_token, group_chat_id, count=200):
    url = (
        f"https://api.green-api.com/waInstance{instance_id}"
        f"/GetChatHistory/{api_token}"
    )
    body = json.dumps({"chatId": group_chat_id, "count": count}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise CommandError(f"Green API HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise CommandError(f"Green API connection error: {e.reason}")


def _normalize_phone(sender_id):
    """Strip @c.us / @g.us suffix; return digits-only string."""
    return re.sub(r'@\S+', '', sender_id).strip()


def _find_user(phone):
    """Try phone as stored (digits), then with leading +."""
    return (
        User.objects.filter(phone_number=phone).first()
        or User.objects.filter(phone_number=f"+{phone}").first()
    )


class Command(BaseCommand):
    help = "Read WhatsApp group messages and import match scores found in the last N hours."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and report without writing anything to the database.",
        )
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="How many hours back to scan for messages (default: 24).",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=200,
            help="Max number of messages to fetch from the group (default: 200).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        hours = options["hours"]
        count = options["count"]

        instance_id = getattr(settings, "GREEN_API_INSTANCE_ID", None)
        api_token = getattr(settings, "GREEN_API_TOKEN", None)
        group_chat_id = getattr(settings, "WHATSAPP_GROUP_ID", None)

        if not all([instance_id, api_token, group_chat_id]):
            raise CommandError(
                "Missing settings: GREEN_API_INSTANCE_ID, GREEN_API_TOKEN, and "
                "WHATSAPP_GROUP_ID must all be set in .env"
            )

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        cutoff_ts = int(cutoff.timestamp())

        self.stdout.write(f"Fetching up to {count} messages from WhatsApp group...")
        messages = _fetch_group_messages(instance_id, api_token, group_chat_id, count)

        recent = [m for m in messages if m.get("timestamp", 0) >= cutoff_ts]
        self.stdout.write(
            f"  {len(recent)} messages in the last {hours}h "
            f"(of {len(messages)} fetched)\n"
        )

        imported = skipped = no_score = 0

        for msg in recent:
            if msg.get("type") != "incoming":
                continue

            text = msg.get("textMessage", "")
            if not text:
                continue

            sets = _parse_sets(text)
            if not sets:
                no_score += 1
                continue

            sender_id = msg.get("senderId", "")
            sender_name = msg.get("senderName", sender_id)
            ts = datetime.fromtimestamp(msg["timestamp"], tz=timezone.utc)

            self.stdout.write(
                f"Score candidate from {sender_name} at {ts.strftime('%Y-%m-%d %H:%M')} UTC"
            )
            self.stdout.write(f"  \"{text[:100]}\"")
            self.stdout.write(f"  Parsed sets: {sets}")

            phone = _normalize_phone(sender_id)
            user = _find_user(phone)

            if not user:
                self.stdout.write(f"  SKIP: no user with phone_number matching {phone}\n")
                skipped += 1
                continue

            scheduled = Match.objects.filter(
                status="scheduled",
                season__status="active",
            ).filter(
                db_models.Q(player1=user) | db_models.Q(player2=user)
            )
            match_count = scheduled.count()

            if match_count != 1:
                self.stdout.write(
                    f"  SKIP: {user} has {match_count} scheduled matches in active seasons "
                    f"(need exactly 1 to auto-assign)\n"
                )
                skipped += 1
                continue

            match = scheduled.first()
            is_player1 = match.player1 == user
            opponent = match.player2 if is_player1 else match.player1

            self.stdout.write(f"  Match #{match.pk}: {user} vs {opponent}")

            if dry_run:
                self.stdout.write("  DRY RUN: would import this result\n")
                continue

            # Determine winner from set count
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

            self.stdout.write(
                self.style.SUCCESS(f"  IMPORTED — pending confirmation by {opponent}\n")
            )
            imported += 1

        self.stdout.write(
            f"Done. Imported: {imported}  Skipped: {skipped}  "
            f"No score found: {no_score}"
        )
