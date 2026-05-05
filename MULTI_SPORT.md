# Multi-Sport Expansion — Architecture & Implementation Plan

## Recommendation: Single project with a sport-dispatch layer

**Don't fork, don't use abstract base classes.** Forking means every bug fix and feature must be manually ported to each copy — maintenance cost grows with every new sport. Full abstract base classes (Django multi-table inheritance) add significant complexity, and the sports share more than they differ: the season lifecycle, roster management, playoff structure, and match flow are nearly identical across tennis, pickleball, and football.

The right move is a single project where sport-specific logic plugs in via a dispatch layer. The coupling surface is small.

---

## What's Already Generic (No Changes Needed)

- `accounts` — fully generic
- `leagues.Season` (lifecycle, display, rules, preseason) — generic except for a few scoring config fields
- `leagues.SeasonPlayer`, `leagues.Tier` — fully generic
- `matches.Match` (status flow, authorization rules, scheduling) — fully generic
- `playoffs` (bracket generation, seeding, slot advancement) — generic
- Round-robin scheduler in `matches/scheduler.py` — generic

---

## What's Sport-Specific (The Seam to Cut At)

| Component | Why It's Coupled | Isolation Strategy |
|---|---|---|
| `matches.MatchSet` | "Sets" and "games" are tennis concepts | Replace with a generic `MatchScore` model or a JSON score field per sport |
| `ResultEntryForm` | Tennis score validation (6-game sets, tiebreaks, win-by-two) | Per-sport form classes, loaded via a registry |
| `standings/calculator.py` | Game differential, set ratio — tennis-specific tiebreakers | Per-sport calculator module, dispatched by `season.sport` |
| Score display templates | Inline set scoreboard is tennis-specific | Per-sport score partial templates |
| `Season` scoring fields | `sets_to_win`, `final_set_format`, `win_by_two` | Move to a `TennisConfig` one-to-one model, or keep but ignore for other sports |

---

## Implementation Phases

### Phase 1 — Add the `sport` Discriminator

1. Add `sport = CharField(choices=[('tennis','Tennis'), ('pickleball','Pickleball'), ('football','Football')], default='tennis')` to `leagues.Season`
2. Add and run a migration — existing seasons get `sport='tennis'` automatically
3. No behavior changes yet

### Phase 2 — Introduce a Sport Registry

Create `sports/registry.py`:

```python
_registry = {}

def register(sport_key, form_class, calculator_fn, score_template):
    _registry[sport_key] = {
        'form_class': form_class,
        'calculator': calculator_fn,
        'score_template': score_template,
    }

def get_sport(sport_key):
    return _registry[sport_key]
```

Each sport is self-contained in its own module:
- `sports/tennis.py` — registers existing tennis logic
- `sports/pickleball.py` — registers pickleball logic when built
- `sports/football.py` — registers football logic when built

### Phase 3 — Abstract the Score Storage

Two options, ordered by complexity:

**Option A — JSON field (recommended to start):**
Add `score_data = JSONField(null=True)` to `matches.Match`. Each sport stores its score in whatever shape it needs (e.g. tennis: array of sets, football: quarter scores). Keep `MatchSet` for tennis; populate `score_data` from it on save. One migration, no structural complexity.

**Option B — Per-sport concrete models:**
Create abstract `BaseScore` and sport-specific concrete models (`TennisScore`, `PickleballScore`). Cleaner schema, more Django overhead. Migrate to this from Option A if 3+ sports have complex scoring schemas.

### Phase 4 — Per-Sport `ResultEntryForm`

Move current form and create sport-specific variants:

```
matches/forms/
├── __init__.py
├── tennis.py       ← current ResultEntryForm moved here
├── pickleball.py
└── football.py
```

In the `enter_result` view, dispatch via the registry:

```python
sport = get_sport(match.season.sport)
form = sport['form_class'](request.POST or None, match=match)
```

### Phase 5 — Per-Sport Standings Calculators

Reorganize the standings module:

```
standings/
├── calculators/
│   ├── __init__.py
│   ├── tennis.py     ← current calculator.py moved here
│   ├── pickleball.py
│   └── football.py
└── views.py
```

`standings/calculator.py` becomes a thin dispatcher:

```python
def calculate_standings(season, tier):
    return get_sport(season.sport)['calculator'](season, tier)
```

### Phase 6 — Per-Sport Score Display Templates

Extract the inline scoreboard from `_results_list.html` into sport-specific partials:

```
templates/matches/scores/
├── _score_tennis.html      ← current inline scoreboard extracted here
├── _score_pickleball.html
└── _score_football.html
```

In `_results_list.html`:

```django
{% include sport_score_template %}
```

where `sport_score_template` is injected into context from the view using `get_sport(season.sport)['score_template']`.

### Phase 7 — Sport Branding (Optional)

The clay/forest/cream CSS tokens are tennis-court colors. For a multi-sport app, two paths:

- **Neutral theme:** Replace sport-specific tokens with generic names (`--primary`, `--surface`, `--background`)
- **Per-season colors:** Add `primary_color` / `accent_color` to `Season`; override CSS custom properties via an inline `<style>` block in `base.html` when present

---

## Handling Flavors Within a Sport

A sport flavor (e.g. singles vs. doubles tennis, standard vs. rally-scoring pickleball) maps onto the existing `Season` config pattern. The `Season` already carries flavor knobs like `win_by_two`, `final_set_format`, and `sets_to_win` for tennis. For a new sport, add a `<Sport>Config` one-to-one model linked to `Season` — this keeps flavor-specific fields off the core `Season` model while remaining discoverable via `season.<sport>config`.

---

## Incremental Rollout

You don't need to refactor the whole app at once:

1. Ship Phase 1 — adds the `sport` field with no behavior change; tennis keeps working
2. Ship Phase 2 — registry wired up; tennis registers itself; still no behavior change
3. Build pickleball support behind `sport='pickleball'` by working through Phases 3–6 for that sport only
4. Tennis code is untouched until you choose to migrate it into the new structure

Each phase is independently deployable. The risk surface at any step is small.
