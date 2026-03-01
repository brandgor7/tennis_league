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

## CSS Design System

Source: `static/css/app.css`. All pages extend `base.html`, which loads this file automatically via `{% static %}`. No per-template imports needed.

### Design Tokens

CSS custom properties on `:root`. Use these in any inline styles or future CSS rather than hardcoding values.

| Token | Value | Use |
|-------|-------|-----|
| `--clay` | `#C4522A` | Primary — buttons, links, active indicators |
| `--clay-dark` | `#A0421E` | Primary hover state |
| `--forest` | `#1B3D2B` | Navbar and footer background |
| `--cream` | `#F7F3EB` | Page background |
| `--sand` | `#EDE5D3` | Secondary surface / alternating rows |
| `--charcoal` | `#1A1A18` | Body text |
| `--muted` | `#6B6558` | Subdued / secondary text |
| `--border` | `#D9CEBE` | Input borders, dividers |
| `--white` | `#FEFCF8` | Card background |

All Bootstrap 5 semantic colour variables (`--bs-primary`, `--bs-body-bg`, etc.) are remapped to these tokens, so standard Bootstrap classes (`btn-primary`, `alert-*`, etc.) use the theme automatically.

### Fonts

- **Headings** (`h1`–`h3`, `.font-serif`): Playfair Display — loaded via `<link>` in `base.html`
- **Body / UI**: DM Sans

### Status Badges

```html
<span class="status-badge status-{value}">Label</span>
```

`{value}` maps directly to `Match.status` field values: `scheduled` (blue), `pending` (amber), `completed` (green), `walkover` (orange), `postponed` (grey-brown), `cancelled` (red).

### Component Classes

| Class | Use |
|-------|-----|
| `.page-header` | Top-of-page wrapper; put `<h1>` and `.page-meta` inside |
| `.page-meta` | Subtitle / metadata line below the page `<h1>` |
| `.rank-number` | Serif rank numeral in standings |
| `.rank-number.rank-top-3` | Rank 1–3 highlighted in clay colour |
| `.stat-value` | Tabular-numeral cell for W, L, pts, ratios |
| `.score-set` | Large serif score display (e.g. `6–3`) |
| `.score-input` | Compact 64 px centred numeric input for score entry |
| `.match-card` | Card with lift-on-hover; wrapper needs `position: relative` when using `stretched-link` |
| `.text-clay` | Clay-coloured text |
| `.bg-sand` | Sand background fill |
| `.border-theme` | Theme border colour (`--border`) |

### Navigation Active State

Child templates mark a nav link active by emitting `nav-active` from the matching block:

```django
{# e.g. in standings.html: #}
{% block nav_standings %}nav-active{% endblock %}
```

Available blocks: `nav_standings`, `nav_schedule`, `nav_results`, `nav_playoffs`. CSS draws a clay underline on the active link.

### Base Template Context

`base.html` renders the season selector and primary nav links only when these context variables are present:

| Variable | Type | Notes |
|----------|------|-------|
| `current_season` | `Season` or `None` | Absent → season nav hidden, no error |
| `all_seasons` | QuerySet of `Season` | Populates the season dropdown |

These are supplied by a context processor added in **Phase 4**. Until then, season nav is simply hidden.

---

## Project Directory Structure

```
tennis-scores-app/
├── manage.py
├── requirements.txt
├── .env                         # SECRET_KEY, DATABASE_URL (gitignored)
├── .env.example                 # Template for .env
├── TESTS.md                     # How to run the test suite
├── config/                      # Django project package
│   ├── __init__.py
│   ├── settings.py
│   ├── test_settings.py         # Overrides DB to SQLite in-memory for tests
│   ├── urls.py
│   └── wsgi.py
├── static/
│   └── css/
│       └── app.css              # Design system — tokens, component classes
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
num_tiers                 IntegerField    default 1; number of competitive tiers in this season
sets_to_win               IntegerField    2 = best of 3, 3 = best of 5
final_set_format          CharField       full | tiebreak | super
playoff_qualifiers_count  IntegerField    e.g. 8, 16, 32 — applies per tier
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
tier      IntegerField              1-indexed tier number for this player in this season (default 1)
seed      IntegerField (nullable)   initial seeding for playoffs within their tier
is_active BooleanField
joined_at DateTimeField
UNIQUE: (season, player)
```

### `matches.Match`
```
season          FK → Season
player1         FK → User
player2         FK → User
tier            IntegerField (nullable)   which tier this match belongs to; set from players' tier at match creation
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
season        FK → Season             (was OneToOneField; one bracket per tier per season)
tier          IntegerField            which tier this bracket is for (1-indexed)
generated_at  DateTimeField
generated_by  FK → User
UNIQUE: (season, tier)
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

Standings are **per-tier**: the calculator takes a season and tier number, returning the ranked player list for that tier only. The standings view iterates over all tiers in the season and renders a separate table (or tab) for each.

**Algorithm (for a given season + tier):**
```
For each active SeasonPlayer in season where tier == requested_tier:
  matches = Match.objects.filter(
      season=season,
      tier=requested_tier,
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

`calculate_standings(season, tier)` → ranked list for one tier.
The standings view calls this for each tier in `range(1, season.num_tiers + 1)`.

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

Brackets are generated **per tier**. `generate_bracket(season, tier, generated_by)` handles one tier at a time. The admin action can call it for each tier in the season.

1. Read standings for `(season, tier)` → top `season.playoff_qualifiers_count` players in that tier
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
4. Create `Match` objects (round=`r16` or appropriate, status=`scheduled`, tier=tier)
5. Create `PlayoffBracket` (with `tier` field) + `PlayoffSlot` objects with correct `next_slot` links
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
/seasons/<id>/standings/                   Standings (all tiers; tabs or sections per tier)
/seasons/<id>/schedule/                    Upcoming matches
/seasons/<id>/results/                     Completed match results
/seasons/<id>/playoffs/                    Playoff bracket list (redirects to tier 1 if single-tier)
/seasons/<id>/playoffs/<tier>/             Playoff bracket for a specific tier

/matches/<id>/                             Match detail (set scores, status)
/matches/<id>/enter-result/                Enter score (player in match or admin)
/matches/<id>/confirm-result/              Confirm or dispute score (opponent or admin)
/matches/<id>/walkover/                    Mark walkover (admin)
/matches/<id>/postpone/                    Mark postponed / set new date (admin)

/admin/                                    Django admin
/admin/seasons/<id>/generate-playoffs/<tier>/  Custom admin action: generate bracket for one tier
```

---

## Forms

| Form | Fields |
|------|--------|
| `ResultEntryForm` | Dynamic: N sets × (p1_games, p2_games, tb_p1, tb_p2). Validates legal scores. |
| `WalkoverForm` | winner (player1/player2/none), reason |
| `PostponeForm` | new_scheduled_date, reason |
| `SeasonForm` | All Season config fields, including `num_tiers` |
| `MatchScheduleForm` | player1, player2, scheduled_date — player dropdowns filtered to same tier |

**Score validation rules:**
- Normal set: winner must have ≥ 6 games, lead by ≥ 2 (except 7-5)
- Tiebreak set: 7-6, tiebreak scores required
- Super tiebreak (final set): first to 10 points with 2-point lead

---

## Settings Highlights

```python
AUTH_USER_MODEL      = 'accounts.User'
LOGIN_URL            = '/accounts/login/'
LOGIN_REDIRECT_URL   = '/'
LOGOUT_REDIRECT_URL  = '/accounts/login/'
STATICFILES_DIRS     = [BASE_DIR / 'static']

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

**Running tests:** `config/test_settings.py` overrides `DATABASES` with SQLite in-memory so the test suite runs without PostgreSQL. See `TESTS.md` for the full command reference.

---

## Dependencies

```
django>=5.0
psycopg2-binary
django-environ
```
