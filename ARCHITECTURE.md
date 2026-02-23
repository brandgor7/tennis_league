# Tennis League Scoring App — Architecture

## Overview

A Django + PostgreSQL web application for managing a tennis league. Multiple seasons coexist, each with independently configurable rules. Admins set up seasons, rosters, and matches. Players log in and enter results. A confirmation flow ensures score accuracy. Dashboards show standings, results, and schedules. A playoff bracket is auto-generated from end-of-season standings.

---

## Tech Stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Backend | Django 5.x (Python) | |
| Database | PostgreSQL | |
| Auth | Django `AbstractUser` | Built-in session auth |
| Frontend | Django Templates + Bootstrap 5 | Server-rendered; Bootstrap via CDN |
| Admin | Django admin + custom views | Augmented for league management |
| Config | `django-environ` | `.env` file for secrets |

---

## Responsive Design

Bootstrap 5's `md` breakpoint (768px) is the single dividing line between **mobile** and **desktop** layouts. No separate stylesheets; all responsiveness is handled with Bootstrap utility classes and the grid.

**Approach per surface:**

### Navigation
- Mobile (`< md`): Bootstrap hamburger navbar (`navbar-expand-md`); links collapse into an off-canvas/dropdown menu; season selector is a full-width item in the menu
- Desktop (`≥ md`): Full horizontal navbar; season selector inline as a dropdown

### Standings Table
- Mobile: Simplified card list — one card per player showing rank, name, points, W-L. Ratio columns hidden. Cards are tap-friendly with generous padding.
- Desktop: Full table with all columns (rank, name, P, W, L, pts, set ratio, game ratio), sortable headers

### Schedule & Results
- Mobile: Match cards — player names stacked vertically, date and status as badge/label below. Tapping a card opens the match detail.
- Desktop: Table rows with player1 vs player2, date, status, and a details link

### Match Detail
- Mobile: Stacked layout — match header (players + status), then set scores as a simple horizontal-scrollable score table
- Desktop: Two-column layout — match info on the left, set-by-set score grid on the right

### Result Entry Form
- Mobile: One set per row, full-width number inputs with large tap targets (min 44px height), prominent submit button. Numeric keyboard triggered via `inputmode="numeric"`. Tiebreak fields appear inline below the set row only when needed.
- Desktop: Sets displayed in a grid; all fields visible at once; tab-friendly navigation

### Playoff Bracket
- Mobile: Horizontal-scroll container (`overflow-x: auto`) wrapping the bracket; bracket rendered as a horizontal flow (rounds left to right); player names truncated with full name in tooltip
- Desktop: Full bracket rendered in CSS grid, all rounds visible simultaneously without scrolling

### Player Profile
- Mobile: Match history as cards (opponent, result, date)
- Desktop: Match history as a table

### Forms (login, walkover, postpone)
- Mobile: Full-width inputs and buttons, stacked labels
- Desktop: Standard form layout with max-width container to prevent over-stretching on wide screens (`max-w: 600px` centered)

---

## Project Directory Structure

```
tennis-scores-app/
├── manage.py
├── requirements.txt
├── .env                         # SECRET_KEY, DATABASE_URL (gitignored)
├── .env.example                 # Template for .env
├── config/                      # Django project package
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── accounts/                    # User model, login/logout, profile
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   └── forms.py
├── leagues/                     # Season + SeasonPlayer (roster management)
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   ├── forms.py
│   └── admin.py
├── matches/                     # Match + MatchSet models; result entry & confirmation
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   └── forms.py
├── standings/                   # Standings calculation logic + views
│   ├── calculator.py            # Pure calculation logic (no models here)
│   └── views.py
├── playoffs/                    # Bracket generation + display
│   ├── models.py
│   ├── generator.py             # Bracket seeding + Match creation logic
│   └── views.py
└── templates/
    ├── base.html
    ├── accounts/
    │   ├── login.html
    │   └── profile.html
    ├── leagues/
    │   ├── season_list.html
    │   └── season_detail.html
    ├── matches/
    │   ├── schedule.html
    │   ├── results.html
    │   ├── match_detail.html
    │   ├── enter_result.html
    │   └── confirm_result.html
    ├── standings/
    │   └── standings.html
    └── playoffs/
        └── bracket.html
```

---

## Django Apps

### `accounts`
- Custom `User` model extending `AbstractUser`
- Login / logout views
- Player profile view (their matches, record)

### `leagues`
- `Season` model — all per-season configuration
- `SeasonPlayer` model — roster (which users are in which season)
- Season list, detail views
- Admin: create/edit seasons, manage rosters

### `matches`
- `Match` model — scheduling, status, players, result
- `MatchSet` model — individual set scores (supports tiebreak scores)
- Result entry view (for a player in the match)
- Result confirmation view (for the opponent)
- Walkover and postponement views (admin or player)

### `standings`
- No models — standings are computed dynamically from `Match` + `MatchSet` data
- `calculator.py` — pure function that takes a Season and returns ranked player list
- Standings view renders the table

### `playoffs`
- `PlayoffBracket` model — one per season, records when generated
- `PlayoffSlot` model — one per bracket position; links to a `Match`; has `next_slot` FK for winner advancement
- Generator: reads standings, seeds bracket, creates `Match` + `PlayoffSlot` objects
- Bracket view renders the visual bracket

---

## Data Models

### `accounts.User`
```
AbstractUser fields: username, email, first_name, last_name, password, is_staff, is_active
```

### `leagues.Season`
```
name                      CharField       e.g. "Spring 2025"
year                      IntegerField
status                    CharField       upcoming | active | completed
sets_to_win               IntegerField    2 = best of 3, 3 = best of 5
final_set_format          CharField       full | tiebreak | super
playoff_qualifiers_count  IntegerField    e.g. 8, 16, 32
walkover_rule             CharField       winner | split | none
postponement_deadline     IntegerField    days allowed to reschedule
points_for_win            IntegerField    default 3
points_for_loss           IntegerField    default 0
points_for_walkover_loss  IntegerField    default 0 (set to 1 if walkover_rule=split)
created_at                DateTimeField
```

### `leagues.SeasonPlayer`
```
season    FK → Season
player    FK → User
seed      IntegerField (nullable)   initial seeding for playoffs
is_active BooleanField
joined_at DateTimeField
UNIQUE: (season, player)
```

### `matches.Match`
```
season          FK → Season
player1         FK → User
player2         FK → User
round           CharField    regular | r32 | r16 | qf | sf | f
scheduled_date  DateField (nullable)
played_date     DateField (nullable)
status          CharField    scheduled | pending_confirmation | completed | walkover | postponed | cancelled
winner          FK → User (nullable)
entered_by      FK → User (nullable)   who entered the result
confirmed_by    FK → User (nullable)   who confirmed the result
walkover_reason TextField
notes           TextField
created_at      DateTimeField
updated_at      DateTimeField
```

### `matches.MatchSet`
```
match                   FK → Match (related_name='sets')
set_number              IntegerField     1, 2, 3...
player1_games           IntegerField
player2_games           IntegerField
tiebreak_player1_points IntegerField (nullable)
tiebreak_player2_points IntegerField (nullable)
UNIQUE: (match, set_number)
ORDER BY: set_number
```

### `playoffs.PlayoffBracket`
```
season        OneToOneField → Season
generated_at  DateTimeField
generated_by  FK → User
```

### `playoffs.PlayoffSlot`
```
bracket           FK → PlayoffBracket
match             OneToOneField → Match
bracket_position  IntegerField    1-indexed position in bracket
round             CharField       mirrors Match.round
next_slot         FK → self (nullable)   winner of this slot advances to next_slot's match
```

---

## Standings Calculation

Computed dynamically in `standings/calculator.py`. No cache table needed at typical league scale.

**Algorithm:**
```
For each active SeasonPlayer in season:
  matches = Match.objects.filter(
      season=season,
      status__in=['completed', 'walkover'],
      player in [player1, player2]
  )
  wins   = matches where winner == player
  losses = matches - wins (not counting walkovers where player isn't winner)

  points = (wins * season.points_for_win)
         + (walkover_losses * season.points_for_walkover_loss)
         + (regular_losses * season.points_for_loss)

  sets_won, sets_lost   = sum from MatchSet
  games_won, games_lost = sum from MatchSet

Ranking tiebreakers (in order):
  1. points (desc)
  2. matches_played (desc — more matches played ranks higher)
  3. sets_won / sets_played ratio (desc)
  4. games_won / games_played ratio (desc)
  5. head-to-head result (if still equal)
```

---

## Match Result Flow

```
[scheduled]
     │
     ▼  Player enters score
[pending_confirmation]
     │
     ├──▶ Opponent confirms ──▶ [completed]
     │
     └──▶ Opponent disputes ──▶ Admin reviews ──▶ [completed] or stays pending

Admin can also directly:
     [scheduled] ──▶ [walkover]
     [scheduled] ──▶ [postponed]
     [postponed] ──▶ [scheduled]  (with new date)
     any state   ──▶ [cancelled]
```

**Authorization rules:**
- Only `player1` or `player2` of the match can enter results (or admin/staff)
- Only the *other* player from whoever entered can confirm (or admin/staff)
- Walkover and postponement: admin/staff only, or either player (configurable)

---

## Playoff Bracket Generation

In `playoffs/generator.py`:

1. Read standings for season → top `season.playoff_qualifiers_count` players
2. Determine bracket size (next power of 2 ≥ qualifier count)
3. Standard tennis bracket seeding for 16-draw:
   - Position 1: seed 1 vs seed 16
   - Position 2: seed 8 vs seed 9
   - Position 3: seed 5 vs seed 12
   - Position 4: seed 4 vs seed 13
   - Position 5: seed 3 vs seed 14
   - Position 6: seed 6 vs seed 11
   - Position 7: seed 7 vs seed 10
   - Position 8: seed 2 vs seed 15
4. Create `Match` objects (round=`r16`, status=`scheduled`)
5. Create `PlayoffSlot` objects, set `next_slot` so winners advance
6. When a playoff match completes: a post-save signal (or explicit view logic)
   sets the winner as `player1` or `player2` in the next round's `Match`

---

## URL Map

```
/                                          Home → redirect to active season standings
/accounts/login/                           Login
/accounts/logout/                          Logout
/accounts/profile/                         Player profile + their match history

/seasons/                                  All seasons list
/seasons/<id>/                             Season overview
/seasons/<id>/standings/                   Standings table
/seasons/<id>/schedule/                    Upcoming matches
/seasons/<id>/results/                     Completed match results
/seasons/<id>/playoffs/                    Playoff bracket

/matches/<id>/                             Match detail (set scores, status)
/matches/<id>/enter-result/                Enter score (player in match or admin)
/matches/<id>/confirm-result/              Confirm or dispute score (opponent or admin)
/matches/<id>/walkover/                    Mark walkover (admin)
/matches/<id>/postpone/                    Mark postponed / set new date (admin)

/admin/                                    Django admin
/admin/seasons/<id>/generate-playoffs/     Custom admin action: generate playoff bracket
```

---

## Forms

| Form | Fields |
|------|--------|
| `ResultEntryForm` | Dynamic: N sets × (p1_games, p2_games, tb_p1, tb_p2). Validates legal scores. |
| `WalkoverForm` | winner (player1/player2/none), reason |
| `PostponeForm` | new_scheduled_date, reason |
| `SeasonForm` | All Season config fields |
| `MatchScheduleForm` | player1, player2, scheduled_date |

**Score validation rules:**
- Normal set: winner must have ≥ 6 games, lead by ≥ 2 (except 7-5)
- Tiebreak set: 7-6, tiebreak scores required
- Super tiebreak (final set): first to 10 points with 2-point lead

---

## Settings Highlights

```python
AUTH_USER_MODEL    = 'accounts.User'
LOGIN_URL          = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    ...
    'accounts',
    'leagues',
    'matches',
    'standings',
    'playoffs',
]
```

---

## Dependencies

```
django>=5.0
psycopg2-binary
django-environ
```
