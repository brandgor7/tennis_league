import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

_HEADER_RE = re.compile(
    r'^\[[\d/,: APMapm]+\]\s+(.+?):\s+(.*)',
    re.IGNORECASE,
)
_PHONE_RE = re.compile(r'^[\d\s\+\(\)\-\.]+$')
_SCORE_RE = re.compile(r'(?<!\d)(\d{1,2})\s*[-:]\s*(\d{1,2})(?!\d)')
_WA_TAG_RE = re.compile(r'@[^\s~]*~([^⁩\s]+)⁩?')
_TIER_PREFIX_RE = re.compile(r'^\s*[Tt](?:ier)?\s*\d+\s+', re.IGNORECASE)
_BEAT_VERB_RE = re.compile(
    r'(?<!\w)(def(?:eated)?\.?|d\.?|beat(?:s)?|over)(?!\w)',
    re.IGNORECASE,
)
_WIN_VERB_RE = re.compile(r'(?<!\w)(wins?|won)(?!\w)', re.IGNORECASE)
_ME_RE = re.compile(r'^me\.?$', re.IGNORECASE)


@dataclass
class ParsedMessage:
    raw: str
    poster_name: Optional[str]
    winner_raw: str            # named winner
    loser_raw: Optional[str]   # named loser; None means "me" (the poster)
    score1: int  # winner's score
    score2: int  # loser's score


@dataclass
class ResolvedResult:
    parsed: ParsedMessage
    match: object         # Match instance or None
    winner: object        # User instance or None
    loser: object         # User instance or None
    winner_score: int
    loser_score: int
    confidence: int       # 0–100
    error: Optional[str] = None


def parse_whatsapp_messages(text: str) -> list:
    """Parse multi-line WhatsApp text into ParsedMessage objects."""
    results = []
    for line in text.splitlines():
        parsed = _parse_line(line)
        if parsed is not None:
            results.append(parsed)
    return results


def _strip_format_chars(s: str) -> str:
    return ''.join(c for c in s if unicodedata.category(c) != 'Cf')


def _parse_line(line: str) -> Optional[ParsedMessage]:
    line = _strip_format_chars(line).strip()
    if not line:
        return None

    poster_name = None
    body = line
    header_match = _HEADER_RE.match(line)
    if header_match:
        sender = header_match.group(1).strip()
        body = header_match.group(2).strip()
        if not _PHONE_RE.match(sender):
            poster_name = sender

    body = _WA_TAG_RE.sub(lambda m: m.group(1), body)
    body = _TIER_PREFIX_RE.sub('', body).strip()

    score_match = _SCORE_RE.search(body)
    if not score_match:
        return None

    score1 = int(score_match.group(1))
    score2 = int(score_match.group(2))
    pre_score = body[:score_match.start()].strip()

    beat_match = _BEAT_VERB_RE.search(pre_score)
    if beat_match:
        winner_raw = pre_score[:beat_match.start()].strip()
        loser_raw = pre_score[beat_match.end():].strip()
        if not winner_raw:
            return None
        is_me = bool(_ME_RE.match(loser_raw))
        return ParsedMessage(
            raw=line,
            poster_name=poster_name,
            winner_raw=winner_raw,
            loser_raw=None if is_me else (loser_raw or None),
            score1=score1,
            score2=score2,
        )

    win_match = _WIN_VERB_RE.search(pre_score)
    if win_match:
        winner_raw = pre_score[:win_match.start()].strip()
        if not winner_raw:
            return None
        return ParsedMessage(
            raw=line,
            poster_name=poster_name,
            winner_raw=winner_raw,
            loser_raw=None,
            score1=score1,
            score2=score2,
        )

    return None


def name_score(name: str, user) -> int:
    """Return a 0–100 similarity score between a raw name string and a User."""
    name = name.lower().strip().rstrip('.')
    full = user.get_full_name().lower().strip()
    last = (user.last_name or '').lower().strip()
    first = (user.first_name or '').lower().strip()

    if full and full == name:
        return 100
    if last and last == name:
        return 80
    if first and first == name:
        return 70
    if full and (name in full or full in name):
        return 60
    if last and (name in last or last in name):
        return 40
    if first and (name in first or first in name):
        return 30
    if (user.username or '').lower() == name:
        return 35
    return 0


def _best_match(name: str, users, exclude_ids=None):
    """Return (user, score) for the best name→User match."""
    best, best_sc = None, 0
    for u in users:
        if exclude_ids and u.pk in exclude_ids:
            continue
        sc = name_score(name, u)
        if sc > best_sc:
            best, best_sc = u, sc
    return best, best_sc


def resolve_results(parsed_messages, season) -> list:
    """Resolve ParsedMessages to ResolvedResult objects using DB lookups."""
    from leagues.models import SeasonPlayer
    from matches.models import Match

    players = [
        sp.player
        for sp in SeasonPlayer.objects.filter(
            season=season, is_active=True
        ).select_related('player')
    ]
    scheduled = list(
        Match.objects.filter(
            season=season,
            status__in=[Match.STATUS_SCHEDULED, Match.STATUS_POSTPONED],
        ).select_related('player1', 'player2').order_by('scheduled_date', 'created_at')
    )
    return [_resolve_one(p, players, scheduled) for p in parsed_messages]


def _resolve_one(parsed, players, scheduled):
    winner, w_sc = _best_match(parsed.winner_raw, players)
    if not winner or w_sc == 0:
        return ResolvedResult(
            parsed=parsed, match=None, winner=None, loser=None,
            winner_score=parsed.score1, loser_score=parsed.score2,
            confidence=0,
            error=f'No player matched "{parsed.winner_raw}"',
        )

    if parsed.loser_raw is None:
        loser, l_sc = None, 0
        if parsed.poster_name:
            loser, l_sc = _best_match(parsed.poster_name, players, exclude_ids={winner.pk})
        if not loser:
            m = _match_for_one(winner, scheduled)
            if m:
                loser = m.player2 if m.player1_id == winner.pk else m.player1
                l_sc = 30
            else:
                return ResolvedResult(
                    parsed=parsed, match=None, winner=winner, loser=None,
                    winner_score=parsed.score1, loser_score=parsed.score2,
                    confidence=w_sc // 2,
                    error='Could not identify opponent — poster unknown',
                )
    else:
        loser, l_sc = _best_match(parsed.loser_raw, players, exclude_ids={winner.pk})
        if not loser or l_sc == 0:
            return ResolvedResult(
                parsed=parsed, match=None, winner=winner, loser=None,
                winner_score=parsed.score1, loser_score=parsed.score2,
                confidence=w_sc // 2,
                error=f'No player matched "{parsed.loser_raw}"',
            )

    match, m_sc = _match_for_pair(winner, loser, scheduled)
    if not match:
        winner_name = winner.get_full_name() or winner.username
        loser_name = loser.get_full_name() or loser.username
        return ResolvedResult(
            parsed=parsed, match=None, winner=winner, loser=loser,
            winner_score=parsed.score1, loser_score=parsed.score2,
            confidence=min(w_sc, l_sc) // 2,
            error=f'No scheduled match found for {winner_name} vs {loser_name}',
        )

    confidence = (w_sc + l_sc + m_sc) // 3
    return ResolvedResult(
        parsed=parsed, match=match, winner=winner, loser=loser,
        winner_score=parsed.score1, loser_score=parsed.score2,
        confidence=confidence,
    )


def _match_for_pair(p1, p2, scheduled):
    ids = {p1.pk, p2.pk}
    for m in scheduled:
        if {m.player1_id, m.player2_id} == ids:
            return m, 90
    return None, 0


def _match_for_one(player, scheduled):
    for m in scheduled:
        if m.player1_id == player.pk or m.player2_id == player.pk:
            return m
    return None
