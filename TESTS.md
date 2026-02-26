# Running the Test Suite

Tests use Django's built-in test runner with an in-memory SQLite database
(`config/test_settings.py`), so no running PostgreSQL instance is required.

## Quick start

```bash
# If python is on your PATH (activated venv or system install):
python manage.py test --settings=config.test_settings

# If using the project's .venv directly:
.venv/bin/python manage.py test --settings=config.test_settings
```

## Useful options

```bash
# Verbose output — shows each test name and pass/fail:
python manage.py test --settings=config.test_settings -v 2

# Run a single app:
python manage.py test accounts --settings=config.test_settings

# Run a single test class:
python manage.py test accounts.tests.LoginViewTest --settings=config.test_settings

# Run a single test method:
python manage.py test accounts.tests.LoginViewTest.test_valid_login_redirects --settings=config.test_settings

# Stop on first failure:
python manage.py test --settings=config.test_settings --failfast

# Keep the test database between runs (faster for repeated runs):
python manage.py test --settings=config.test_settings --keepdb
```

## Test settings

`config/test_settings.py` inherits all production settings and overrides the
database with SQLite in-memory, so no `.env` database URL is needed for tests.
The `SECRET_KEY` and other `.env` values are still read — ensure a `.env` file
exists (copy `.env.example` if not).

## Test files by app

| File | What it covers |
|------|---------------|
| `accounts/tests.py` | User model, login/logout flows, navbar template rendering |
| `leagues/tests.py` | Season and SeasonPlayer models |
| `matches/tests.py` | Match and MatchSet model validation |
| `playoffs/tests.py` | PlayoffBracket and PlayoffSlot models |
