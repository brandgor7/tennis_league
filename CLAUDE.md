# Claude Code — Project Context

## Project

Tennis league scoring web application. Django + PostgreSQL.

## Architecture Reference

Full architecture is documented in **[ARCHITECTURE.md](./ARCHITECTURE.md)**.

Read ARCHITECTURE.md before making any changes. After work is done, make sure ARCHITECTURE.md is updated to reflect the current state of the project based solely on the work performed.
The intent is that this file should be referenced instead of loading each source code file to find details of the project for the
task at hand that aren't directly related to the task that's being performed or that are
dependencies on the task being performed.

## Implementation Plan Reference

Step-by-step build order is in **[IMPLEMENTATION.md](./IMPLEMENTATION.md)**.
Record steps executed in that file for future reference.


## Key Conventions

- **Server-rendered templates only** — no JavaScript framework, no API layer
- **Bootstrap 5 via CDN** — no npm, no build step
- **No extra dependencies if possible** — only `django`, `psycopg2-binary`, `django-environ`
- `AUTH_USER_MODEL = 'accounts.User'` — always use `get_user_model()`, never import `User` directly
- Standings are **computed dynamically** from match data — no denormalized standings table
- Score validation logic lives in the form (`ResultEntryForm`), not the model
- Playoff bracket generation logic lives in `playoffs/generator.py`, not in views
- Include as few comments as possible, and only for complex or convoluted code (which ideally shouldn't occur)


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
