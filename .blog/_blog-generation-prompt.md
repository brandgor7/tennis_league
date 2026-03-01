# Blog Generation Prompt

Use this prompt at the end of a Claude Code session to generate a blog post documenting the session.

---

## Prompt (copy and paste as-is)

```
I'm writing a blog to document my journey in writing this app. I am a first-time Agentic AI programmer, but I am a software engineer. My audience is my LinkedIn connections, so the beginning of each blog needs to be non-technical, and the rest should be somewhat but not overly technical. Based on everything that happened in this context in Claude, summarize what I did in blog posts, one or more as needed. Each blog post shouldn't take more than 5 minutes to read. Markdown is fine for now. Write the blog entries in the directory .blog, using the filename format YYYY-MM-DD-short-title.md. Once that's done, update the file .blog/_blog-generation-prompt.md to include this prompt for reuse later.
```

---

## Guidelines for the blog posts

- **Opening (non-technical):** Start with the human story — what problem am I solving, what was I trying to do today, what surprised me. No jargon. LinkedIn connections who aren't engineers should find it interesting.
- **Middle (lightly technical):** Explain what actually happened — tools used, decisions made, what was built or planned. Use technical terms but define or imply them in context. Don't assume the reader knows Django or what a data model is.
- **Closing:** What I learned or what comes next. Keep it honest — this is a journey, not a polished product announcement.
- **Length:** 600–900 words per post. If a session covered too much for one post, split it by natural phase (e.g. planning vs. building vs. debugging).
- **Tone:** First person, genuine, slightly self-deprecating where appropriate. Not a tutorial. Not a product pitch. A journal.

## Naming convention

```
.blog/YYYY-MM-DD-short-descriptive-title.md
```

Use the date the session occurred. If multiple posts come from one session, use a suffix:
```
.blog/2026-02-22-planning-with-ai.md
.blog/2026-02-22-building-the-models.md
```

## Posts written so far

| Date | File | Topic |
|------|------|-------|
| 2026-02-22 | `2026-02-22-planning-with-ai.md` | First session: planning the architecture, producing spec docs, no code written |
| 2026-02-23 | `2026-02-23-first-real-code.md` | Phase 1 + 2: venv saga, Django scaffold, five apps, full data models and migrations |
| 2026-02-23 | `2026-02-23-ai-reviews-its-own-code.md` | Code review (11 issues found), fixes, comment stripping, unit tests, merge |
| 2026-02-24 | `2026-02-24-clay-courts-and-css.md` | Design timing decision, Clay Court Editorial visual identity, base template, login page, SQLite preview workaround |
| 2026-02-25 | `2026-02-25-done-means-done.md` | Code review of design branch (6 issues, 1 already fixed), Django test client rationale, 49 tests passing, discovering profile view was missing from Phase 3, building it, updating ARCHITECTURE.md |
| 2026-02-28 | `2026-02-28-tiers-before-code.md` | Designing multi-tier season support: minimal model changes (4 fields), new Phase 5, updated Phases 6–12, planning before coding |
