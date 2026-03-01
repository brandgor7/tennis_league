# Tiers Before Code

*Building a tennis league scoring app, Day 5 — a feature request, a design session, and the discipline of changing the plan before changing anything else*

---

When you run a real tennis league, players aren't all equally matched. You might have a handful of competitive players who've been playing for decades, a middle group who play regularly but aren't trying to win regionals, and a batch of newer players who are still figuring out when to come to the net. Throwing everyone into one draw and computing a single standings table doesn't actually tell you much — the top players win everything, and the newer players have no one to measure themselves against.

The answer is tiers. Split the league into levels. Let players compete against people at their level. Run separate standings and separate playoffs for each tier. Promote and relegate between seasons if you want, but that's a future problem.

Today was about adding that to the plan — without touching a single line of code.

---

## The Feature, Explained

The requirement was straightforward to describe: each season should have a configurable number of tiers. Each player in that season belongs to one tier. Players can only be matched against players in the same tier. Standings are split by tier. Playoffs happen separately for each tier.

The tricky part isn't the idea — it's figuring out where it touches the system. This kind of "cross-cutting" feature tends to ripple everywhere: the data model, the scheduling logic, the standings calculator, the playoff bracket generator, the admin interface, the URL structure, the templates. If you don't think it through before you start writing code, you end up making changes in the wrong order and creating a mess.

So the first step was to update the documents.

---

## The Architecture Decision: Keep the Models Minimal

The project has an architecture document — a reference file that describes every model, every URL, every design decision. Before writing any code, we updated that first.

The key question for the data model was: what's the simplest representation of a tier? The answer turned out to be four small changes:

1. **Season gets a `num_tiers` field** — just an integer, defaulting to 1. A season with one tier behaves exactly like the old design. No migration drama for existing data.

2. **SeasonPlayer (the join table between a player and a season) gets a `tier` field** — again, just an integer. Player A is in tier 1 this season. Player B is in tier 2. They can switch tiers next season.

3. **Match gets a `tier` field** — when a match is created, we record which tier it's for. This makes it fast to ask "give me all the completed matches in tier 2 this season" without having to look up both players and check their tiers.

4. **PlayoffBracket changes slightly** — it used to be one-per-season (enforced by the database). Now it's one-per-tier-per-season. The change is small: swap a `OneToOneField` for a `ForeignKey` and add a `tier` column with a unique constraint on the pair.

That's it. No new tables. No complicated polymorphism. No denormalized caches. The tier is a number, and it lives on the objects that need it.

---

## Updating the Plan

The project also has an implementation plan — a checklist of phases with specific tasks. Phases 1 through 4 are done. Everything from Phase 5 onward needed to be revisited.

The approach: insert a new Phase 5 specifically for tier support, and update every subsequent phase to account for tiers. The new phase is purely a data-layer phase — migrations, admin interface updates, form adjustments. No visible UI changes yet. Get the foundation right before building on it.

The phases that needed meaningful updates were:

- **Standings (now Phase 6):** The calculator function takes a tier parameter. The standings view loops over all tiers and renders a separate section or tab for each one.
- **Schedule and Results (Phase 7):** Match lists should be grouped or labelled by tier in multi-tier seasons.
- **Playoff Generation (Phase 11):** The generator function now takes a tier parameter. The admin action runs per-tier. The playoff URL gains a tier segment: `/seasons/3/playoffs/1/` for tier 1, `/seasons/3/playoffs/2/` for tier 2.
- **QA and Testing (Phase 12):** New test scenarios for multi-tier behaviour, plus a regression check that a single-tier season looks identical to before.

One constraint throughout: seasons with `num_tiers=1` should behave exactly as if tiers didn't exist. No tabs with a single option. No "Tier 1" label plastered everywhere when there's only one tier. The feature should be invisible unless you've opted into it.

---

## Why Plan First

I've been doing this long enough to know that skipping the planning step feels faster but usually isn't. Writing code that touches six files in four apps while simultaneously designing the approach leads to thrashing — you make a decision halfway through and have to unwind things.

The planning conversation took less than half an hour. It produced two updated documents on a new branch, ready for review before anything else changes. If the design is wrong, we find out now, not after the migrations are written and the views are half-built.

There's something a bit unusual about planning with an AI assistant versus planning with a colleague. With a colleague, you're negotiating — they have opinions, they'll push back, you'll go back and forth. With Claude, I'm doing more of the driving. I had the feature idea, I had the constraints, I described what I wanted. The AI's job was to think through the implications systematically and write it down cleanly. It's a different collaboration dynamic, and one I'm still getting used to.

---

## What Comes Next

The plan is reviewed and approved. Next session: implement Phase 5. Write the migrations, update the admin, wire up the forms. The first real code in what's now a multi-tier system.

---

*Tools used: Claude Code (Anthropic) | Stack: Django 5, PostgreSQL, Bootstrap 5*
