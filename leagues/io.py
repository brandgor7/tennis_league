"""
Season data export/import.

Field definitions are the single source of truth — changing a field name here
updates both CSV headers and JSON keys simultaneously.
"""

import csv
import io
import json
import logging

from django.contrib.auth import get_user_model
from django.db import models, transaction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema field definitions
# ---------------------------------------------------------------------------

SEASON_FIELDS = [
    'name', 'year', 'status', 'num_tiers', 'sets_to_win', 'games_to_win_set',
    'final_set_format', 'playoff_qualifiers_count', 'walkover_rule', 'schedule_type',
    'postponement_deadline', 'grace_period_days', 'points_for_win', 'points_for_loss',
    'points_for_walkover_loss', 'schedule_display_mode', 'schedule_display_days', 'display',
]

PLAYER_FIELDS = ['username', 'first_name', 'last_name', 'email']

SEASON_PLAYER_FIELDS = ['player_username', 'tier', 'seed', 'is_active']

MATCH_FIELDS = [
    'id', 'player1_username', 'player2_username', 'tier', 'round',
    'scheduled_date', 'played_date', 'status',
    'winner_username', 'entered_by_username', 'confirmed_by_username',
    'walkover_reason', 'notes',
]

# Used for both CSV (as columns, with match_id prepended) and JSON (nested under match)
MATCHSET_FIELDS = [
    'set_number', 'player1_games', 'player2_games',
    'tiebreak_player1_points', 'tiebreak_player2_points',
]

# All username fields in a match record that reference a User
_MATCH_USER_FIELDS = (
    'player1_username', 'player2_username',
    'winner_username', 'entered_by_username', 'confirmed_by_username',
)


# ---------------------------------------------------------------------------
# Serializers (model instance → dict)
# ---------------------------------------------------------------------------

def _username(user):
    return user.username if user else ''


def _serialize_season(season):
    return {f: getattr(season, f) for f in SEASON_FIELDS}


def _serialize_player(user):
    return {f: getattr(user, f) for f in PLAYER_FIELDS}


def _serialize_season_player(sp):
    return {
        'player_username': sp.player.username,
        'tier': sp.tier,
        'seed': sp.seed if sp.seed is not None else '',
        'is_active': sp.is_active,
    }


def _serialize_match(match):
    return {
        'id': match.pk,
        'player1_username': _username(match.player1),
        'player2_username': _username(match.player2),
        'tier': match.tier if match.tier is not None else '',
        'round': match.round,
        'scheduled_date': str(match.scheduled_date) if match.scheduled_date else '',
        'played_date': str(match.played_date) if match.played_date else '',
        'status': match.status,
        'winner_username': _username(match.winner),
        'entered_by_username': _username(match.entered_by),
        'confirmed_by_username': _username(match.confirmed_by),
        'walkover_reason': match.walkover_reason,
        'notes': match.notes,
    }


def _serialize_matchset(ms):
    return {
        'set_number': ms.set_number,
        'player1_games': ms.player1_games,
        'player2_games': ms.player2_games,
        'tiebreak_player1_points': ms.tiebreak_player1_points if ms.tiebreak_player1_points is not None else '',
        'tiebreak_player2_points': ms.tiebreak_player2_points if ms.tiebreak_player2_points is not None else '',
    }


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_season_data(season):
    """Return a structured dict of all season data, ready for JSON or CSV serialisation."""
    from matches.models import Match

    season_players = list(
        season.season_players.select_related('player').order_by('player__username')
    )
    matches = (
        Match.objects
        .filter(season=season)
        .prefetch_related('sets')
        .select_related('player1', 'player2', 'winner', 'entered_by', 'confirmed_by')
    )

    match_list = []
    for match in matches:
        m = _serialize_match(match)
        m['sets'] = [_serialize_matchset(ms) for ms in match.sets.all()]
        match_list.append(m)

    players = sorted({sp.player for sp in season_players}, key=lambda u: u.username)
    return {
        'season': _serialize_season(season),
        'players': [_serialize_player(p) for p in players],
        'season_players': [_serialize_season_player(sp) for sp in season_players],
        'matches': match_list,
    }


def to_json(data):
    return json.dumps(data, indent=2, default=str)


def to_csv(data):
    """
    Serialise *data* to a single CSV string with section markers.

    Each section starts with a ``#section:<name>`` row, followed by a header
    row and data rows.  Blank lines separate sections for readability.
    Sections: season, players, season_players, matches, match_sets.
    """
    buf = io.StringIO()

    match_rows = [{k: v for k, v in m.items() if k != 'sets'} for m in data['matches']]
    set_rows = [
        {'match_id': m['id'], **s}
        for m in data['matches']
        for s in m.get('sets', [])
    ]

    sections = [
        ('season', SEASON_FIELDS, [data['season']]),
        ('players', PLAYER_FIELDS, data['players']),
        ('season_players', SEASON_PLAYER_FIELDS, data['season_players']),
        ('matches', MATCH_FIELDS, match_rows),
        ('match_sets', ['match_id'] + MATCHSET_FIELDS, set_rows),
    ]

    for name, fieldnames, rows in sections:
        buf.write(f'#section:{name}\n')
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
        buf.write('\n')

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Import parsers (file bytes → structured dict)
# ---------------------------------------------------------------------------

def from_json(text):
    return json.loads(text)


def from_csv(text):
    """Parse a section-marker CSV (as produced by ``to_csv``) back to a data dict."""
    sections = {}
    current_name = None
    current_lines = []

    for line in text.splitlines():
        if line.startswith('#section:'):
            if current_name is not None:
                sections[current_name] = _csv_to_dicts('\n'.join(current_lines))
            current_name = line[len('#section:'):]
            current_lines = []
        elif current_name is not None:
            current_lines.append(line)

    if current_name is not None:
        sections[current_name] = _csv_to_dicts('\n'.join(current_lines))

    matches_by_id = {m['id']: {**m, 'sets': []} for m in sections.get('matches', [])}
    for row in sections.get('match_sets', []):
        row = dict(row)
        match_id = row.pop('match_id')
        if match_id in matches_by_id:
            matches_by_id[match_id]['sets'].append(row)

    season_rows = sections.get('season', [])
    return {
        'season': season_rows[0] if season_rows else {},
        'players': sections.get('players', []),
        'season_players': sections.get('season_players', []),
        'matches': list(matches_by_id.values()),
    }


def _csv_to_dicts(text):
    return [r for r in csv.DictReader(io.StringIO(text)) if any(r.values())]


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def import_season_data(data, season):
    """
    Upsert all records in *data* into *season*.

    - Players: upsert by username.
    - SeasonPlayers: upsert by (season, player).
    - Matches: upsert by pk when the id exists in this season; otherwise create.
    - MatchSets: upsert by (match, set_number).

    Returns a summary dict with counts and any non-fatal error messages.
    """
    from .models import SeasonPlayer
    from matches.models import Match, MatchSet
    User = get_user_model()

    summary = {
        'players': {'created': 0, 'updated': 0},
        'season_players': {'created': 0, 'updated': 0},
        'matches': {'created': 0, 'updated': 0},
        'match_sets': {'created': 0, 'updated': 0},
        'errors': [],
    }

    with transaction.atomic():
        season_data = data.get('season', {})
        for field in SEASON_FIELDS:
            raw = season_data.get(field)
            if raw is None:
                continue
            setattr(season, field, _coerce_model_field(season, field, raw))
        season.save()

        user_map = {}
        for pd in data.get('players', []):
            username = (pd.get('username') or '').strip()
            if not username:
                continue
            user, created = User.objects.update_or_create(
                username=username,
                defaults={k: pd.get(k, '') for k in PLAYER_FIELDS if k != 'username'},
            )
            user_map[username] = user
            summary['players']['created' if created else 'updated'] += 1

        # Pre-fetch any users referenced in matches that weren't in the players section
        # (e.g. winner/entered_by/confirmed_by from seasons not in this export)
        referenced = {
            md.get(f, '')
            for md in data.get('matches', [])
            for f in _MATCH_USER_FIELDS
        } - set(user_map) - {'', None}
        for user in User.objects.filter(username__in=referenced):
            user_map[user.username] = user

        def _resolve_user(username):
            return user_map.get(username) if username else None

        for spd in data.get('season_players', []):
            username = (spd.get('player_username') or '').strip()
            user = _resolve_user(username)
            if not user:
                summary['errors'].append(f'Player "{username}" not found; skipped from roster.')
                continue
            seed_raw = spd.get('seed')
            seed = int(seed_raw) if seed_raw not in ('', None) else None
            _, created = SeasonPlayer.objects.update_or_create(
                season=season,
                player=user,
                defaults={
                    'tier': int(spd.get('tier') or 1),
                    'seed': seed,
                    'is_active': _parse_bool(spd.get('is_active', True)),
                },
            )
            summary['season_players']['created' if created else 'updated'] += 1

        existing_match_ids = set(
            Match.objects.filter(season=season).values_list('pk', flat=True)
        )

        for md in data.get('matches', []):
            raw_id = md.get('id')
            try:
                match_id = int(raw_id) if raw_id not in ('', None) else None
            except (ValueError, TypeError):
                match_id = None

            match_fields = {
                'player1': _resolve_user(md.get('player1_username')),
                'player2': _resolve_user(md.get('player2_username')),
                'tier': int(md['tier']) if md.get('tier') not in ('', None) else None,
                'round': md.get('round') or Match.ROUND_REGULAR,
                'scheduled_date': _parse_date(md.get('scheduled_date')),
                'played_date': _parse_date(md.get('played_date')),
                'status': md.get('status') or Match.STATUS_SCHEDULED,
                'winner': _resolve_user(md.get('winner_username')),
                'entered_by': _resolve_user(md.get('entered_by_username')),
                'confirmed_by': _resolve_user(md.get('confirmed_by_username')),
                'walkover_reason': md.get('walkover_reason') or '',
                'notes': md.get('notes') or '',
            }

            if match_id and match_id in existing_match_ids:
                Match.objects.filter(pk=match_id).update(**match_fields)
                match = Match(pk=match_id, season=season, **match_fields)
                summary['matches']['updated'] += 1
            else:
                match = Match.objects.create(season=season, **match_fields)
                summary['matches']['created'] += 1

            for sd in md.get('sets', []):
                tb1_raw = sd.get('tiebreak_player1_points')
                tb2_raw = sd.get('tiebreak_player2_points')
                _, created = MatchSet.objects.update_or_create(
                    match=match,
                    set_number=int(sd.get('set_number', 0)),
                    defaults={
                        'player1_games': int(sd.get('player1_games', 0)),
                        'player2_games': int(sd.get('player2_games', 0)),
                        'tiebreak_player1_points': int(tb1_raw) if tb1_raw not in ('', None) else None,
                        'tiebreak_player2_points': int(tb2_raw) if tb2_raw not in ('', None) else None,
                    },
                )
                summary['match_sets']['created' if created else 'updated'] += 1

    return summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coerce_model_field(instance, field_name, value):
    """Coerce *value* to the Python type expected by the named field on *instance*."""
    field = instance._meta.get_field(field_name)
    if isinstance(field, models.BooleanField):
        return _parse_bool(value)
    if isinstance(field, models.IntegerField):
        return int(value) if value not in ('', None) else None
    return value


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).lower() in ('true', '1', 'yes')


def _parse_date(value):
    from datetime import date
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None
