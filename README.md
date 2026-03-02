# Tennis League Scoring App

A Django web application for managing a tennis league — seasons, rosters, match scheduling, result entry, standings, and playoffs. Built with Django 5, PostgreSQL, and Bootstrap 5.

---

## Local Development

No PostgreSQL needed. The dev setup uses a local SQLite file (`preview.sqlite3`).

### Prerequisites

- Python 3.12+

### Setup

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy the environment file
cp .env.example .env
# The default .env.example values work as-is for local dev;
# no edits required.

# 4. Apply migrations to the local SQLite database
python manage.py migrate --settings=config.preview_settings

# 5. Seed sample data (12 players, 1 active season, 20 completed matches)
python manage.py seed --noinput --settings=config.preview_settings

# 6. Start the development server
python manage.py runserver --settings=config.preview_settings
```

Open **http://localhost:8000** in your browser.

### Sample accounts

| Username | Password | Role |
|----------|----------|------|
| `admin` | `admin` | Superuser — full admin access at `/admin/` |
| `djokovic` | `tennis123` | Tier 1 player |
| `nadal` | `tennis123` | Tier 1 player |
| `federer` | `tennis123` | Tier 1 player |
| `hewitt` | `tennis123` | Tier 2 player |
| `edberg` | `tennis123` | Tier 2 player |
| *(any other seeded username)* | `tennis123` | Player |

### Re-seeding

Running `seed` again wipes all data and starts fresh:

```bash
python manage.py seed --settings=config.preview_settings
# Prompts for confirmation; use --noinput to skip.
```

### Running tests

Tests use an in-memory SQLite database — no `.env` database URL required.

```bash
python manage.py test --settings=config.test_settings
python manage.py test --settings=config.test_settings -v 2   # verbose
```

See `TESTS.md` for the full test command reference.

---

## Production Deployment

### Additional dependencies

Install these in your production environment:

```bash
pip install gunicorn whitenoise
```

- **gunicorn** — production WSGI server
- **whitenoise** — serves static files directly from Django (no separate nginx config needed for small deployments)

### Environment variables

Create a `.env` file on the server (never commit this):

```ini
SECRET_KEY=<generate with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
DEBUG=False
DATABASE_URL=postgres://USER:PASSWORD@HOST:5432/DBNAME
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
```

### Add WhiteNoise to settings

Add `whitenoise.middleware.WhiteNoiseMiddleware` to `MIDDLEWARE` immediately after `SecurityMiddleware`, and add `STATICFILES_STORAGE`:

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',   # ← add this line
    ...
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
```

### Deploy steps

```bash
# 1. Install dependencies
pip install -r requirements.txt gunicorn whitenoise

# 2. Apply migrations
python manage.py migrate

# 3. Collect static files
python manage.py collectstatic --noinput

# 4. Create a superuser
python manage.py createsuperuser

# 5. Start gunicorn
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
```

### systemd service (optional)

Save as `/etc/systemd/system/tennis.service`:

```ini
[Unit]
Description=Tennis League App
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/tennis-scores-app
EnvironmentFile=/path/to/tennis-scores-app/.env
ExecStart=/path/to/.venv/bin/gunicorn config.wsgi:application \
          --bind 127.0.0.1:8000 --workers 3
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable tennis
sudo systemctl start tennis
```

### nginx reverse proxy (optional)

For TLS termination and serving on port 443, place nginx in front of gunicorn:

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

> **TLS certificates:** Use [Certbot](https://certbot.eff.org/) with the Let's Encrypt CA for free certificates.

---

## Project documentation

| File | Contents |
|------|----------|
| `ARCHITECTURE.md` | Data models, URL map, responsive design decisions |
| `IMPLEMENTATION.md` | Phase-by-phase build plan with completion status |
| `TESTS.md` | How to run the test suite |
