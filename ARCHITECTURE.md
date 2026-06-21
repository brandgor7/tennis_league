# Tennis League Scoring App — Architecture

## Overview

A Django + SQLite web application for managing a tennis league. Multiple seasons coexist, each with independently configurable rules. Admins set up seasons, rosters, and matches. Players log in and enter results. A confirmation flow ensures score accuracy. Dashboards show standings, results, and matchups. A playoff bracket is auto-generated from end-of-season standings.

---

## Tech Stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Backend | Django 5.x (Python) | |
| Database | SQLite (WAL mode) | Used in dev, test, and production |
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
- Mobile: Simplified card list — one card per player showing rank, name, W–L, points. Cards are tap-friendly with generous padding.
- Desktop: Table with columns: rank, player, Wins, Losses, Pts, PD (game differential)

### Matchups & Results
- **Matchups** (scheduled/postponed/pending_confirmation):
  - Mobile: cards with player names, scheduled date, status badge; entire card taps to match detail
  - Desktop: table rows with player1, player2, date, status, detail link
- **Results** (completed/walkover): inline tennis scoreboard — no click-through required to see scores
  - Both mobile and desktop show a two-row scoreboard per match: winner name bold/charcoal, loser name muted; each set's game count in fixed-width tabular columns; tiebreak loser score as superscript
  - Walkover matches (no sets) show "W/O" label instead of score columns
  - Mobile: scoreboard card with date + status in a footer strip below
  - Desktop: table with a "Match" column containing the scoreboard; date, status, and "View" link in separate columns

### Match Detail
- Mobile: Stacked layout — match header (players + status), then set scores as a simple horizontal-scrollable score table
- Desktop: Two-column layout — match info on the left, set-by-set score grid on the right

### Result Entry Form
- Mobile: One set per row, full-width number inputs with large tap targets (min 44px height), prominent submit button. Numeric keyboard triggered via `inputmode="numeric"`. Tiebreak fields appear inline below the set row only when needed.
- Desktop: Sets displayed in a grid; all fields visible at once; tab-friendly navigation

### Playoff Bracket
Two layout styles, selected per season via `Season.playoff_bracket_style`:

- **Traditional** (`traditional`, default): rounds flow left → right with the final on the right. Each match is a two-player card; connectors drawn with CSS pseudo-elements. Template body in `playoffs/_bracket_pane.html`.
- **Centered** (`centered`): the draw splits into two halves that converge from the left and the right onto a central champion node, with the final in the centre. Players are rendered as **separate single nodes** (not paired cards); the winner of each match appears on the line where its two feeders meet, advancing toward the centre. Template body in `playoffs/_bracket_pane_centered.html`; layout computed by `playoffs.views._centered_layout`.

Both styles:
- Mobile: Horizontal-scroll container (`overflow-x: auto`) wrapping the bracket; player names truncated (short form on mobile via `.bracket-short-name`)
- Desktop: Full bracket rendered in CSS grid; centred horizontally, scrolls when wider than the viewport

All bracket CSS (traditional `.bracket-*` and centered `.cb-*`) lives in the `extra_css` block of `playoffs/bracket.html`.

### Player Profile (`/seasons/<id>/players/<player_id>/`)
- Page shows the player's standing (rank, W/L, Pts, PD) for the season, followed by upcoming matches and completed results
- Reuses `_match_list.html` and `_results_list.html` partials
- Mobile: stat summary row, then matches as cards
- Desktop: stat summary row, then matches as a table
- Public — no login required

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

- **Headings** (`h1`–`h3`, `.font-serif`): Lora — loaded via `<link>` in `base.html`
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
| `.stat-value` | Tabular-numeral cell for Wins, Losses, Pts, PD |
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

Available blocks: `nav_standings`, `nav_matchups`, `nav_results`, `nav_playoffs`, `nav_rules`. CSS draws a clay underline on the active link.

### Player Name Links

Every player name rendered in the UI links to that player's profile page (`leagues:player_detail`). This applies to: `_match_list.html`, `_results_list.html`, `_standings_table.html`, `match_detail.html`, and `accounts/profile.html`. The link requires `season.pk` and `player.pk`; season context is always available via `current_season` from the context processor.

### Base Template Context

`base.html` renders the season selector and primary nav links only when these context variables are present:

| Variable | Type | Notes |
|----------|------|-------|
| `current_season` | `Season` or `None` | Absent → season nav hidden, no error |
| `all_seasons` | QuerySet of `Season` | Populates the season dropdown; filtered by `display` flag for non-staff users (staff see all; enrolled players always see their seasons) |

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
    ├── matches/
    │   ├── matchups.html
    │   ├── results.html
    │   ├── match_detail.html
    │   ├── enter_result.html
    │   ├── confirm_result.html
    │   ├── _match_list.html         # partial: mobile cards + desktop table (matchups)
    │   └── _results_list.html       # partial: inline scoreboard (results)
    ├── standings/
    │   ├── standings.html
    │   └── _standings_table.html    # partial: mobile cards + desktop table
    ├── leagues/
    │   ├── season_list.html
    │   ├── season_detail.html
    │   ├── player_detail.html       # player profile within a season
    │   └── rules.html               # league rules page; Markdown rendered via marked.js CDN
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
- `SiteConfig` model — singleton; stores global `site_name` and `logo` as base64 data URL; configurable in admin. Acts as fallback when a season has no branding override.
- Season list, detail views
- `SeasonPlayerDetailView` — public player profile page showing standing, upcoming matches, and results for a player within a season
- Admin: create/edit seasons, manage rosters, edit site name and logo

### `matches`
- `Match` model — scheduling, status, players, result
- `MatchSet` model — individual set scores (supports tiebreak scores)
- `scheduler.py` — `generate_schedule(season, start_date, num_rounds)`: round-robin schedule generation across all tiers; idempotent across calls — already-scheduled matchup pairs are filtered out so no pair is ever duplicated within a season, enabling batch scheduling (e.g. schedule first 3 rounds, then 3 more later). `remaining_rounds_count(season, tier)` returns how many rounds remain schedulable for a tier. `existing_pairs(season, tier)` is the single authoritative function for "which pairs must not be re-scheduled" — it checks the current season and, if `season.preseason` is set, the attached preseason.
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
- Bracket view (`PlayoffView`) renders the visual bracket. Per tier, if a `PlayoffBracket` exists it renders the real bracket via `_bracket_context`; otherwise, when playoffs are enabled, it renders a live standings-based preview via `_preview_context`. The real-vs-preview choice is driven solely by bracket existence (not the `Tier.is_playoffs` flag), so seasons with no `Tier` records still show their generated bracket instead of a perpetual preview. Each tier also gets a `centered` layout via `_centered_layout`. The template picks traditional vs centered markup based on `Season.playoff_bracket_style`.

---

## Data Models

### `leagues.SiteConfig`
```
site_name      CharField(100)   Global fallback site name (navbar brand, page footer); default "TennisLeague"
logo           TextField        Global fallback logo as base64 data URL; blank = default icon shown
pk             always 1         Singleton — enforced by model.save() and admin
```
`SiteConfig` is the **global fallback**. When a `Season` has its own `site_name` or `logo` set, those take priority for requests scoped to that season (resolved by the `season_context` context processor). Logo uploads are validated by magic bytes (PNG `\x89PNG\r\n\x1a\n`, JPEG `\xff\xd8\xff`) and capped at 2 MB. The data URL is stored in the database — no file system writes, no MEDIA configuration needed.

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
win_by_two                BooleanField    default True; if False, set winner only needs to reach games_to_win_set (e.g. 6–5 is valid; 7–5 is not)
final_set_format          CharField       full | tiebreak | super
playoff_qualifiers_count  IntegerField    default per-tier qualifier count; can be overridden per tier on the Tier model
playoffs_public           BooleanField    default True; when False, only staff can view playoff brackets and the nav tab is hidden for players
playoff_interval_days     IntegerField    default 7; days between playoff rounds when scheduling with a start date
playoff_bracket_style     CharField       traditional | centered — layout of the playoffs page bracket (see Responsive Design → Playoff Bracket)
schedule_type             CharField       single_day | consecutive_days | weekly
walkover_rule             CharField       winner | split | none
postponement_deadline     IntegerField    days allowed to reschedule
grace_period_days         IntegerField    default 7; days after scheduled_date a match can be played without a formal postponement
enforce_scheduled_dates   BooleanField    default True; when False, the grace-period deadline is not enforced and any match can have a result entered regardless of date. Disabling this also greys out postponement_deadline and grace_period_days in the admin.
points_for_win            IntegerField    default 3
points_for_loss           IntegerField    default 0
points_for_walkover_loss  IntegerField    default 0 (set to 1 if walkover_rule=split)
schedule_display_mode     CharField       all | current_day | current_week | next_x_days — controls which upcoming matches appear on the matchups page
schedule_display_days     IntegerField    default 7; days ahead to show when schedule_display_mode=next_x_days
display                   BooleanField    default True; if False, season is hidden from the dropdown for non-staff users not enrolled in it (direct URL access still works for anyone)
playoffs_enabled          BooleanField    default True; controls visibility of the Playoffs navbar tab and admin playoff actions for this season
show_rules                BooleanField    default False; when True, a "Rules" link appears in the navbar and /seasons/<slug>/rules/ is accessible
rules_content             TextField       Rules text stored as Markdown; blank = no content; rendered via marked.js on the rules page
preseason                 FK → Season (nullable, self-referential)  if set, matchups from the linked season are also excluded when generating the schedule, preventing rematches across seasons
show_rules                BooleanField    default False; when True, a "Rules" link appears in the navbar and /seasons/<slug>/rules/ is accessible
rules_content             TextField       Rules text stored as Markdown; blank = no content; rendered via marked.js on the rules page
site_name                 CharField(100)  Optional branding override for this season; blank = use global SiteConfig.site_name
logo                      TextField       Optional logo override for this season as base64 data URL; blank = use global SiteConfig.logo. Has a logo_url property matching SiteConfig.
created_at                DateTimeField
```

### `leagues.Tier`
```
season                    FK → Season (related_name='tiers')
number                    IntegerField    1-indexed ordering within the season
name                      CharField(50)   Display name, e.g. "Premier", "Division 1"
playoff_qualifiers_count  IntegerField (nullable)  per-tier override; null = use season default
UNIQUE: (season, number)
ORDER BY: number
```

### `leagues.SeasonPlayer`
```
season    FK → Season
player    FK → User
tier      IntegerField              1-indexed tier number; matches Tier.number for the same season
seed      IntegerField (nullable)   initial seeding for playoffs within their tier
is_active BooleanField
joined_at DateTimeField
UNIQUE: (season, player)
```

### `matches.Match`
```
season          FK → Season
player1         FK → User (nullable)   null for TBD playoff slots until winner is determined
player2         FK → User (nullable)   null for TBD playoff slots until winner is determined
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

  games_won, games_lost = sum from MatchSet (walkovers contribute 0)
  pd = games_won - games_lost

Returned dict per player: player, wins, losses, points, pd

Ranking tiebreakers (applied internally, not exposed in the returned dict):
  1. points (desc)
  2. matches_played (desc — more matches played ranks higher)
  3. sets_won / sets_played ratio (desc)
  4. games_won / games_played ratio (desc)
  5. head-to-head result (if still equal — not yet implemented)
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
     [walkover]  ──▶ [scheduled]  (admin: undo walkover)
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

Brackets are generated **per tier**. `generate_bracket(season, tier, generated_by, start_date=None)` handles one tier at a time. The admin action can call it for each tier in the season.

1. Read standings for `(season, tier)` → top N players, where N = `tier.playoff_qualifiers_count` if set, else `season.playoff_qualifiers_count`
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
4. Create `Match` objects (round=`r16` or appropriate, status=`scheduled`, tier=tier). If `start_date` is given, round 1 gets that date and each subsequent round is `season.playoff_interval_days` later.
5. Create `PlayoffBracket` (with `tier` field) + `PlayoffSlot` objects with correct `next_slot` links
6. When a playoff match completes: a post-save signal sets the winner as `player1` or `player2` in the next round's `Match`

The admin generate-playoffs page includes an optional start date field. Leaving it blank generates the bracket draw without scheduling any match dates.

---

## URL Map

```
/                                          Home → redirect to last visited season (cookie) or welcome page
/accounts/login/                           Login
/accounts/logout/                          Logout
/accounts/profile/                         Player profile + their match history

/seasons/<slug>/rules/                     Season rules page (Markdown rendered; only accessible when Season.show_rules=True)

/seasons/                                  All seasons list
/seasons/<slug>/                           Season overview
/seasons/<slug>/standings/                 Standings (all tiers; tabs or sections per tier)
/seasons/<slug>/matchups/                  Upcoming matches
/seasons/<slug>/results/                   Completed match results
/seasons/<slug>/playoffs/                  Playoff bracket list (redirects to tier 1 if single-tier)
/seasons/<slug>/playoffs/<tier>/           Playoff bracket for a specific tier
/seasons/<slug>/players/<username>/        Player profile — standing, upcoming matches, and results within that season

/seasons/<slug>/matches/<id>/              Match detail (set scores, status)
/seasons/<slug>/matches/<id>/enter-result/     Enter score (player in match or admin)
/seasons/<slug>/matches/<id>/edit-result/      Edit score of a completed match (admin only)
/seasons/<slug>/matches/<id>/confirm-result/   Confirm or dispute score (opponent or admin)
/seasons/<slug>/matches/<id>/walkover/         Mark walkover (admin)
/seasons/<slug>/matches/<id>/postpone/         Mark postponed / set new date (admin)
/seasons/<slug>/matches/<id>/undo-walkover/    Reset a walkover back to scheduled (admin POST)

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

### Admin: Analyze / Generate Schedule

Custom admin view at `/admin/seasons/<id>/generate-schedule/`. Combines schedule generation, analysis, and manual match management on one page:

- **Tier overview table** — active players, total rounds, remaining rounds per tier
- **Add Rounds form** — start date + number of rounds; hidden when all rounds are exhausted
- **Schedule Analysis** (shown once any matches exist):
  - *Matches by Date* — match count per date per tier; totals row and grand total
  - *Players with Fewer Scheduled Matches* — per-tier cards showing players whose scheduled match count is below the tier maximum, with deficit badge; replaced by a green confirmation when all players are equal
- **Schedule a Match** — tier dropdown → player list (sorted by fewest matches) → opponent columns (new matchup / already played) → optional date → creates a single `Match` record
- **Delete a Match** — tier dropdown → scheduled-matches dropdown (ordered by date, then player name) → inline confirmation → deletes the match

Analysis data is computed by `SeasonAdmin._build_schedule_analysis(season, tier_range)` which returns `None` when no matches exist. Per-player match counts are computed by `SeasonAdmin._match_count_map(season, tier, tier_players)`, shared across the analysis and the two manual-scheduling endpoints.

A **Bulk Add Results** button on the season change page opens a two-step flow:

1. **Parse step** — admin pastes raw WhatsApp-style messages into a textarea and submits. `matches/bulk_result_parser.py` parses each line to extract winner, loser, and score. The parser handles WhatsApp message headers (sender name or phone number), `@⁨~Name⁩` mention tags, tier prefixes (`T1`, `Tier 2`, etc.), and verb variants (`d`, `d.`, `def`, `defeated`, `beat`, `over`, `wins`, `won`). Scores can be `N-M` or `N:M`. If the opponent is referred to as "me", the poster name is used to identify them; if the poster is unknown (phone-only), the resolver infers the opponent from the player's next scheduled match.
2. **Review step** — parsed results are matched against the season's scheduled/postponed matches and active players using fuzzy name scoring. The admin sees a table of original messages alongside the guessed match, winner, score, and confidence. Rows with a match found have a pre-checked confirm checkbox; rows with errors show the reason. Submitting saves only the checked rows: creates a single `MatchSet`, marks the match completed, and auto-confirms it (admin privilege).

Five supporting JSON/POST endpoints on `SeasonAdmin`:

| URL | Method | Purpose |
|-----|--------|---------|
| `/admin/seasons/<id>/schedule-match/players/?tier=<n>` | GET | Players in tier with match counts |
| `/admin/seasons/<id>/schedule-match/matchups/?tier=<n>&player=<id>` | GET | Opponent split: not-played vs already-played |
| `/admin/seasons/<id>/schedule-match/` | POST | Create a single regular-season match |
| `/admin/seasons/<id>/delete-match/matches/?tier=<n>` | GET | Scheduled regular-season matches for tier |
| `/admin/seasons/<id>/delete-match/` | POST | Delete a single scheduled regular-season match |
| `/admin/seasons/<id>/bulk-results/` | GET/POST | Paste + parse WhatsApp messages → review → bulk save results |

**Score validation rules:**
- Normal set: winner must have ≥ 6 games; if `win_by_two=True` (default), must also lead by ≥ 2 (7-5 is allowed, 6-5 is not); if `win_by_two=False`, reaching 6 is enough (6-5 is valid, 7-5 is not)
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
