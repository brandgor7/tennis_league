# I Used AI to Plan My First Solo App — And Didn't Write a Single Line of Code

*Building a tennis league scoring app, Day 1 — the planning session*

---

I play in a local tennis league. We manage everything through a spreadsheet and a group chat. Someone inevitably posts the wrong score. Another person doesn't see the message. The standings are always at least a week behind. It's a mess, and it's been a mess for years.

I'm a software engineer, so the logical thing is to build something. I've been putting it off because every time I sit down to start, I get bogged down in decisions before I've written a word: what database? how do I handle logins? what happens when someone disputes a score? I end up with a half-baked notes file and close my laptop.

This time I decided to try something different. I'd heard people talking about "agentic AI" programming — where instead of asking an AI a question and typing back and forth, you describe a goal and let the AI take steps to accomplish it, like a colleague working alongside you. I had no idea what that would actually feel like in practice. So I tried it.

Here's what happened.

---

## What Is "Agentic AI" Programming?

The tool I used is called Claude Code. You run it in your terminal and it can read files, write files, search your project, run commands, and browse documentation — all on its own. The key difference from a chat interface is that it *takes actions*, not just gives answers. You describe what you want, and it works through the steps to get there.

I'd used ChatGPT and similar tools before for one-off questions. This felt categorically different. More like onboarding a contractor than googling an answer.

---

## The First Thing That Surprised Me: It Asked Me Questions

I described the app: a tennis league site where an admin sets up seasons, players log in and enter match results, there are standings and schedules, and playoffs are auto-generated from standings.

Before doing anything, Claude came back with three structured questions:

1. **Tech stack** — did I have a preference, or should it pick something sensible?
2. **What kinds of rules change between seasons?** — it gave me a checklist of options (sets format, tiebreak rules, walkover rules, playoff size, etc.)
3. **How should result entry work?** — one player enters and the other confirms? Admin approves? No confirmation?

I hadn't thought through all of these. In particular, "rules for unplayed or delayed matches" wasn't something I'd considered — but of course it matters. What do you do when someone doesn't show up? Does the other person get a full win? A partial win? Nothing? That choice needs to be in the data model from day one, or you'll be retrofitting it later.

This is maybe the most underrated thing about working with AI this way: it forces you to answer questions you were going to have to answer eventually, just on *your* schedule instead of when you're knee-deep in code.

I chose: **Django + PostgreSQL**, because that's what I know. All the rule options. And the confirmation flow where one player enters the score and the opponent must confirm before it's official — that felt right for a league where trust matters.

---

## Then It Went Off and Thought

Claude entered what it called "plan mode." It explored the project directory (which was completely empty, just a Git repo), then spent time designing the architecture before touching any files. It was also going to write code — but I interrupted it.

> "Write the architecture in a spec file. Write in the CLAUDE.md file to reference the architecture from the spec file. Write the implementation plan in an implementation file. Once that's all done, then stop."

And it did exactly that. No argument, no "are you sure?" — it just adjusted and followed the new instruction.

This is another thing that surprised me: you can redirect it mid-task. It doesn't need to finish what it started. It holds the whole context in mind and pivots cleanly.

---

## What We Produced

After that first session, with no code written, I had three files in my project:

**`ARCHITECTURE.md`** — a full design document covering:
- All the data models (seasons, players, matches, sets, playoff brackets) with every field named and typed
- The standings calculation algorithm, including tiebreaker rules
- The playoff bracket seeding logic (1 vs 16, 2 vs 15, etc.)
- The match result flow: scheduled → pending confirmation → completed, with walkover and postponement branches
- A full URL map for the app
- Form validation rules for tennis scores (what makes a valid set score?)

**`IMPLEMENTATION.md`** — an 11-phase build plan, checklist-style, with specific files to create in each phase and what to verify before moving on.

**`CLAUDE.md`** — a project context file that any future Claude session will read automatically. It explains the conventions, where the logic lives, and which documents to consult before making changes. Essentially an onboarding doc for the AI.

---

## One More Iteration

After reviewing the docs, I realized the responsive design story was vague. I asked Claude to add proper mobile and desktop UX specs.

It updated both `ARCHITECTURE.md` and `IMPLEMENTATION.md` with specifics: the navbar collapses to a hamburger below 768px, standings show as cards on mobile instead of a wide table, the score entry form uses `inputmode="numeric"` on mobile to trigger the number keyboard, the playoff bracket scrolls horizontally on small screens. Each major view had concrete rules for both layouts.

Importantly, "mobile-optimized score entry UX" had been sitting in the *Deferred* section of the implementation plan. Claude moved it into the main plan without me having to say that explicitly. It understood that "add mobile and desktop UX" meant it was no longer deferred.

---

## What I Took Away From Day 1

I've planned software projects before. Usually the plan lives in my head, partially in a notes app, and partially in whatever I happen to build first. This time I have a spec that another developer — or another AI session — could pick up and understand.

The planning took one conversation. I didn't open a text editor. I didn't draw a diagram. I answered questions, redirected once, and made one follow-up request. The artifacts that came out are more thorough than anything I'd have written on my own, because I would have skipped the parts I thought were obvious and deferred the parts I didn't want to decide yet.

The AI didn't let me do either of those things.

Next post: actually writing the code.

---

*Tools used: Claude Code (Anthropic) | Stack chosen: Django 5, PostgreSQL, Bootstrap 5*
