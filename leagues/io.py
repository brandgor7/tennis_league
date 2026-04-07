"""
Season data export/import.

Field definitions are the single source of truth — changing a field name here
updates both CSV headers and JSON keys simultaneously.
"""

import csv
import io
import json
import zipfile

from django.contrib.auth import get_user_model
from django.db import models, transaction


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


# ---------------------------------------------------------------------------
# Serializers (model instance → dict)
# ---------------------------------------------------------------------------

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
    def _username(user):
        return user.username if user else ''

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

    players = {
        sp.player
        for sp in season.season_players.select_related('player').all()
    }
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

    return {
        'season': _serialize_season(season),
        'players': [
            _serialize_player(p) for p in sorted(players, key=lambda u: u.username)
        ],
        'season_players': [
            _serialize_season_player(sp)
            for sp in season.season_players.select_related('player').order_by('player__username')
        ],
        'matches': match_list,
    }


def to_json(data):
    return json.dumps(data, indent=2, default=str)


def to_csv_zip(data):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('season.csv', _dicts_to_csv([data['season']], SEASON_FIELDS))
        zf.writestr('players.csv', _dicts_to_csv(data['players'], PLAYER_FIELDS))
        zf.writestr('season_players.csv', _dicts_to_csv(data['season_players'], SEASON_PLAYER_FIELDS))

        match_rows = [{k: v for k, v in m.items() if k != 'sets'} for m in data['matches']]
        zf.writestr('matches.csv', _dicts_to_csv(match_rows, MATCH_FIELDS))

        set_rows = [
            {'match_id': m['id'], **s}
            for m in data['matches']
            for s in m.get('sets', [])
        ]
        zf.writestr('match_sets.csv', _dicts_to_csv(set_rows, ['match_id'] + MATCHSET_FIELDS))
    return buf.getvalue()


def _dicts_to_csv(rows, fieldnames):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Import parsers (file bytes → structured dict)
# ---------------------------------------------------------------------------

def from_json(text):
    return json.loads(text)


def from_csv_zip(file_bytes):
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        season_row = _csv_to_dicts(zf.read('season.csv').decode('utf-8-sig'))[0]
        players = _csv_to_dicts(zf.read('players.csv').decode('utf-8-sig'))
        season_players = _csv_to_dicts(zf.read('season_players.csv').decode('utf-8-sig'))

        matches_by_id = {
            m['id']: {**m, 'sets': []}
            for m in _csv_to_dicts(zf.read('matches.csv').decode('utf-8-sig'))
        }
        for row in _csv_to_dicts(zf.read('match_sets.csv').decode('utf-8-sig')):
            row = dict(row)
            match_id = row.pop('match_id')
            if match_id in matches_by_id:
                matches_by_id[match_id]['sets'].append(row)

    return {
        'season': season_row,
        'players': players,
        'season_players': season_players,
        'matches': list(matches_by_id.values()),
    }


def _csv_to_dicts(text):
    return list(csv.DictReader(io.StringIO(text)))


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
        # 1. Update season config fields
        season_data = data.get('season', {})
        for field in SEASON_FIELDS:
            raw = season_data.get(field)
            if raw is None:
                continue
            setattr(season, field, _coerce_model_field(season, field, raw))
        season.save()

        # 2. Upsert players
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

        def _resolve_user(username):
            if not username:
                return None
            return user_map.get(username) or User.objects.filter(username=username).first()

        # 3. Upsert season players
        for spd in data.get('season_players', []):
            username = (spd.get('player_username') or '').strip()
            user = _resolve_user(username)
            if not user:
                summary['errors'].append(f'Player "{username}" not found; skipped from roster.')
                continue
            seed_raw = spd.get('seed')
            seed = int(seed_raw) if seed_raw not in ('', None) else None
            sp, created = SeasonPlayer.objects.update_or_create(
                season=season,
                player=user,
                defaults={
                    'tier': int(spd.get('tier') or 1),
                    'seed': seed,
                    'is_active': _parse_bool(spd.get('is_active', True)),
                },
            )
            summary['season_players']['created' if created else 'updated'] += 1

        # 4. Upsert matches and their sets
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
                match = Match.objects.get(pk=match_id)
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
