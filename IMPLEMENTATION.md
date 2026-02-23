# Tennis League Scoring App — Implementation Plan

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full data model, URL map, and design decisions.

---

## Phase 1 — Project Scaffold

**Goal:** Runnable Django project connected to PostgreSQL, nothing more.

- [ ] `pip install django psycopg2-binary django-environ`
- [ ] `django-admin startproject config .`
- [ ] Create `.env.example` and `.env` with `SECRET_KEY` and `DATABASE_URL`
- [ ] Update `config/settings.py`:
  - Use `django-environ` to read `.env`
  - Set `DATABASES` from `DATABASE_URL`
  - Set `AUTH_USER_MODEL = 'accounts.User'`
  - Set `LOGIN_URL` and `LOGIN_REDIRECT_URL`
- [ ] Create all five apps: `accounts`, `leagues`, `matches`, `standings`, `playoffs`
- [ ] Add all apps to `INSTALLED_APPS`
- [ ] Verify `python manage.py check` passes

---

## Phase 2 — Data Models + Migrations

**Goal:** All tables created in PostgreSQL. Admin can create records.

- [ ] **`accounts/models.py`** — `User(AbstractUser)` (no extra fields initially)
- [ ] **`leagues/models.py`** — `Season`, `SeasonPlayer`
- [ ] **`matches/models.py`** — `Match`, `MatchSet`
- [ ] **`playoffs/models.py`** — `PlayoffBracket`, `PlayoffSlot`
- [ ] Run `python manage.py makemigrations` and `python manage.py migrate`
- [ ] Register all models in Django admin with sensible `list_display`, `list_filter`, `search_fields`
- [ ] `python manage.py createsuperuser`
- [ ] Verify all models visible and editable in `/admin/`

---

## Phase 3 — Base Template + Auth Views

**Goal:** App has a working layout and players can log in/out. The base template establishes the responsive foundation for every page.

- [ ] **`templates/base.html`**:
  - Bootstrap 5 CDN (CSS + JS bundle)
  - `<meta name="viewport" content="width=device-width, initial-scale=1">` in `<head>`
  - `navbar-expand-md`: full nav on desktop, hamburger on mobile
  - Navbar contains: site name, season selector (dropdown), nav links (Standings, Schedule, Results, Playoffs), login/logout, user display name
  - On mobile: season selector and nav links collapse behind hamburger; each item is full-width and touch-friendly (min 44px tap target)
  - Flash message block (`{% if messages %}`) — full-width alert banners, readable on both screen sizes
  - `{% block content %}` wrapped in `<div class="container">` (fluid on mobile, fixed-width on desktop is handled automatically by Bootstrap's `container`)
  - `{% block extra_css %}` and `{% block extra_js %}` for per-page additions
- [ ] **`accounts/views.py`** — use Django's built-in `LoginView` and `LogoutView`
- [ ] **`accounts/urls.py`** — wire up login, logout
- [ ] **`templates/accounts/login.html`**:
  - Centered card layout, `max-width: 400px`, full-width on mobile
  - Full-width inputs and submit button
- [ ] **`templates/accounts/profile.html`**:
  - Mobile: match history as cards (opponent, result, date, status badge)
  - Desktop: match history as a `table-responsive` table
  - Use `d-none d-md-block` / `d-block d-md-none` to render both and show the appropriate one
- [ ] Wire `accounts/urls.py` into `config/urls.py`
- [ ] Verify login/logout works end-to-end on both a narrow (375px) and wide (1280px) viewport

---

## Phase 4 — Season Views

**Goal:** Public pages for season list and season overview.

- [ ] **`leagues/views.py`**:
  - `SeasonListView` — all seasons, newest first
  - `SeasonDetailView` — season info + links to standings/schedule/results/playoffs
- [ ] **`leagues/urls.py`** — `/seasons/` and `/seasons/<id>/`
- [ ] Templates: `season_list.html`, `season_detail.html`
- [ ] Wire into `config/urls.py`
- [ ] Home view (`/`) redirects to the active season's standings (or season list if none active)

---

## Phase 5 — Standings

**Goal:** Standings table computed live from match results.

- [ ] **`standings/calculator.py`** — `calculate_standings(season)` function:
  - Returns list of dicts: `{player, played, wins, losses, points, sets_ratio, games_ratio}`
  - Applies tiebreaker ordering per ARCHITECTURE.md
  - Handles walkovers per `season.walkover_rule`
- [ ] **`standings/views.py`** — `StandingsView`: calls calculator, renders table
- [ ] **`templates/standings/standings.html`**:
  - Mobile (`d-block d-md-none`): list of Bootstrap cards, one per player; each card shows rank, player name, points, W-L record. Ratio columns omitted to fit the screen.
  - Desktop (`d-none d-md-block`): full `table table-striped table-hover` with all columns (rank, name, P, W, L, pts, set ratio, game ratio)
- [ ] Wire into `leagues/urls.py` at `/seasons/<id>/standings/`
- [ ] Verify empty standings (no matches), partial standings, and full standings all render correctly on both viewports

---

## Phase 6 — Schedule + Results Views

**Goal:** Public pages for upcoming and completed matches.

- [ ] **`matches/views.py`**:
  - `ScheduleView` — matches with `status=scheduled` or `status=postponed`, ordered by `scheduled_date`
  - `ResultsView` — matches with `status=completed` or `status=walkover`, ordered by `played_date` desc
  - `MatchDetailView` — set-by-set scores, status, players, confirmation state
- [ ] **`matches/urls.py`** — routes for all match views
- [ ] **`templates/matches/schedule.html`** and **`results.html`**:
  - Mobile: match cards — player names as "Player A vs Player B", date and status badge below, entire card is a tappable link to match detail (`stretched-link`)
  - Desktop: `table-responsive` table with player1, player2, date, status, detail link
- [ ] **`templates/matches/match_detail.html`**:
  - Mobile: stacked — match header (both players + status badge), then set scores as a compact horizontally scrollable table (`table-responsive`); action buttons (Enter Result / Confirm) full-width below
  - Desktop: two-column layout (`col-md-5` match info | `col-md-7` set scores); action buttons inline in the header area
- [ ] Wire into `config/urls.py`

---

## Phase 7 — Result Entry

**Goal:** A player can enter a match score set-by-set.

- [ ] **`matches/forms.py`** — `ResultEntryForm`:
  - Dynamically generates N sets of fields based on `season.sets_to_win`
  - Fields per set: `p1_games`, `p2_games`, `tb_p1_points` (optional), `tb_p2_points` (optional)
  - Validates legal tennis scores:
    - Normal set: winner has ≥ 6, leads by ≥ 2 (or 7-5)
    - Tiebreak set: 7-6, tiebreak scores required
    - Final set super tiebreak: first to 10 with 2-point lead
  - Validates that the match winner is consistent with set scores and season format
- [ ] **`matches/views.py`** — `EnterResultView`:
  - `@login_required`
  - Must be `player1` or `player2` (or staff)
  - On valid submit: create `MatchSet` objects, set `match.status = 'pending_confirmation'`, set `match.entered_by = request.user`
  - Redirect to match detail with success message
- [ ] **`templates/matches/enter_result.html`**:
  - Mobile: one set per row, stacked vertically; each score input is full-width with `inputmode="numeric"` (triggers numeric keyboard on phones); min input height 44px; tiebreak fields appear as a collapsible row directly below the set only when that set score is 7-6; large full-width submit button
  - Desktop: sets in a compact grid/table (columns: Set #, Player 1 games, Player 2 games, TB P1, TB P2); tab-order moves logically across the row; submit button right-aligned

---

## Phase 8 — Result Confirmation

**Goal:** The opponent confirms or disputes the entered score.

- [ ] **`matches/views.py`** — `ConfirmResultView`:
  - `@login_required`
  - Must be the *other* player (not `entered_by`) or staff
  - **Confirm**: set `match.status = 'completed'`, `match.confirmed_by = request.user`, `match.played_date = today`; determine and set `match.winner` from set scores
  - **Dispute**: set `match.status = 'scheduled'` (revert), delete existing `MatchSet` objects, notify admin (via Django messages or email — messages is sufficient for now)
- [ ] **`templates/matches/confirm_result.html`**:
  - Show entered score prominently (same compact score table as match detail)
  - Mobile: Confirm and Dispute as full-width stacked buttons (Confirm = `btn-success btn-lg w-100`, Dispute = `btn-outline-danger btn-lg w-100 mt-2`)
  - Desktop: Confirm and Dispute side by side, right-aligned

---

## Phase 9 — Walkover + Postponement

**Goal:** Admin (or player) can handle unplayed and delayed matches.

- [ ] **`matches/views.py`**:
  - `WalkoverView` — `@staff_member_required`; `WalkoverForm`; set status, winner, reason
  - `PostponeView` — `@login_required` (player or staff); `PostponeForm`; set new `scheduled_date`, status=`postponed`, add reason to `notes`
- [ ] Templates: `walkover.html`, `postpone.html`
- [ ] Wire into `matches/urls.py`

---

## Phase 10 — Playoff Bracket Generation

**Goal:** Admin can generate the playoff bracket; players see the visual bracket.

- [ ] **`playoffs/generator.py`** — `generate_bracket(season, generated_by)`:
  - Call `calculate_standings(season)`, take top N players
  - Apply standard bracket seeding (1v16, 2v15, 8v9, etc.)
  - Create `Match` objects (round=`r16` or appropriate, status=`scheduled`)
  - Create `PlayoffBracket` + `PlayoffSlot` objects with correct `next_slot` links
  - Return the `PlayoffBracket`
- [ ] **Custom admin view** at `/admin/seasons/<id>/generate-playoffs/`:
  - Requires staff
  - Shows confirmation page (who qualifies, bracket preview)
  - On POST: calls `generate_bracket()`
  - Redirect to playoff bracket page
- [ ] **Winner advancement**: when a playoff match is confirmed as completed, a post-save signal (in `playoffs/models.py` or `matches/models.py`) checks if a `PlayoffSlot` exists for the match; if so, assigns the winner as a player in the `next_slot`'s match
- [ ] **`playoffs/views.py`** — `PlayoffBracketView`:
  - Loads all `PlayoffSlot` objects for season's bracket
  - Passes structured bracket data to template
- [ ] **`templates/playoffs/bracket.html`**:
  - Desktop: CSS grid bracket — rounds as columns, slots as rows; winner names displayed in full; completed matches show score
  - Mobile: same HTML wrapped in `overflow-x: auto` so the bracket scrolls horizontally; player names truncated to first initial + last name to reduce width; a note below the bracket ("Scroll sideways to see all rounds") for first-time clarity
- [ ] Wire into `leagues/urls.py` at `/seasons/<id>/playoffs/`

---

## Phase 11 — Polish, Responsive QA + Testing

**Goal:** App is complete, manually verified end-to-end on both mobile and desktop viewports.

- [ ] Add `{% url %}` links throughout all templates (no hardcoded paths)
- [ ] Confirm all `@login_required` and `@staff_member_required` guards are in place
- [ ] Add Django messages (success/error) to all form submit views
- [ ] **Responsive QA pass** — using browser devtools, test every page at 375px (mobile) and 1280px (desktop):
  - Navbar: hamburger works and collapses correctly on mobile; full nav on desktop
  - Standings: cards on mobile, table on desktop; no horizontal overflow
  - Schedule/Results: cards on mobile, table on desktop
  - Match detail: stacked on mobile, two-column on desktop
  - Score entry: numeric keyboard triggered on mobile; all inputs reachable without zooming; tiebreak fields appear correctly
  - Confirm result: full-width buttons on mobile, inline on desktop
  - Playoff bracket: scrolls horizontally on mobile without breaking layout
  - All buttons and links meet 44px minimum tap target on mobile
  - No text is cut off or overflows its container on either size
- [ ] Test full regular season flow:
  1. Create season in admin
  2. Add players to roster
  3. Create several matches
  4. Enter results as player1, confirm as player2
  5. Verify standings update correctly
  6. Test walkover (standings respect walkover rule)
  7. Test postponement and reschedule
- [ ] Test playoff flow:
  1. Season with ≥ 16 active players and completed matches
  2. Generate bracket via admin action
  3. Verify seeding (rank 1 vs rank 16, etc.)
  4. Enter R16 results → verify QF matches are populated with correct players
  5. Carry through to Final
- [ ] Test auth guards: anonymous user redirected to login; wrong player cannot confirm own result
- [ ] Verify Django admin CRUD works for all models

---

## Deferred / Future Work

- Email notifications (result entered, pending confirmation)
- Head-to-head tiebreaker in standings (complex; defer until basic tiebreakers proven)
- Player self-registration (for now, admin creates accounts)
- Match scheduling by players (currently admin-only)
- Export to CSV/PDF
