# Claude Code — Project Context

## Project

Tennis league scoring web application. Django + PostgreSQL.

## Architecture Reference

Full architecture is documented in **[ARCHITECTURE.md](./ARCHITECTURE.md)**.

Read ARCHITECTURE.md before making any changes. It covers:
- Tech stack and rationale
- All Django apps and their responsibilities
- Complete data models (all fields and relationships)
- Standings calculation algorithm
- Playoff bracket generation algorithm
- URL map
- Match result flow (entry → confirmation → completed)
- Form validation rules for tennis scores

## Implementation Plan Reference

Step-by-step build order is in **[IMPLEMENTATION.md](./IMPLEMENTATION.md)**.

## Key Conventions

- **Server-rendered templates only** — no JavaScript framework, no API layer
- **Bootstrap 5 via CDN** — no npm, no build step
- **No extra dependencies** — only `django`, `psycopg2-binary`, `django-environ`
- `AUTH_USER_MODEL = 'accounts.User'` — always use `get_user_model()`, never import `User` directly
- Standings are **computed dynamically** from match data — no denormalized standings table
- Score validation logic lives in the form (`ResultEntryForm`), not the model
- Playoff bracket generation logic lives in `playoffs/generator.py`, not in views

## Apps at a Glance

| App | Responsibility |
|-----|----------------|
| `accounts` | Custom User model, login/logout, profile |
| `leagues` | Season config, SeasonPlayer roster |
| `matches` | Match + MatchSet models, result entry & confirmation |
| `standings` | Standings calculation (no models) |
| `playoffs` | PlayoffBracket + PlayoffSlot models, bracket generation |

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill in environment variables
cp .env.example .env

# Run migrations
python manage.py migrate

# Create admin user
python manage.py createsuperuser

# Start server
python manage.py runserver
```
