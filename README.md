# Expense Tracker

A Django and SQLite project based on the assignment starter: models, Django forms, function-based views, and HTML templates. Pages share a base template, navigation, and content block as in the portfolio. JavaScript handles error dialogs and repeated clicks. Assignment 7 deploys this version on Azure App Service.

## Run on Windows

Open the project in VS Code and use its PowerShell terminal. Skip the first command if `.venv` already exists.
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Open [Expense Tracker](http://127.0.0.1:8000/). Press **Ctrl+C** in the terminal to stop it. Data stays in `db.sqlite3`; existing accounts and expenses are retained, with old expenses assigned to USD. Tested with Python 3.11 and Django 5.2.18. Debug mode is off by default; set `$env:DJANGO_DEBUG = "True"` locally if needed.

## Azure App Service

Use a Linux App Service with Python 3.11 and the startup command `bash startup.sh`. Set these application settings in Azure:

- `DJANGO_SECRET_KEY`: a private random value, kept the same between deployments.
- `DJANGO_DEBUG`: `False`.
- `DJANGO_DB_PATH`: `/home/data/expenses.sqlite3`.
- `SCM_DO_BUILD_DURING_DEPLOYMENT`: `true`.
- `WEBSITES_ENABLE_APP_SERVICE_STORAGE`: `true`.

Push the code to GitHub and deploy the source files with ZIP deployment and build enabled. Azure installs `requirements.txt`; startup applies migrations, collects static files, and runs Gunicorn. WhiteNoise serves CSS and JavaScript. The Azure hostname is allowed automatically, with HTTPS and secure cookies enabled.

The online SQLite file is stored under persistent `/home`, separate from the deployed code. It survives restarts and deployments. Run one App Service instance and one Gunicorn worker for this class project. The local database, virtual environment, and secrets are excluded from GitHub; the online app starts with its own accounts and expenses.

## Features and rules

- **USD and LBP wallets:** separate expense pages, totals, and budgets; no currency conversion or mixed totals.
- **Expenses:** all six assignment categories, descriptions up to 200 characters, and amounts from `0.01` to `99,999,999.99` with at most two decimal places.
- **Dates:** day/month/year controls, with today prefilled for new expenses. Future dates are rejected.
- **Editing and entry:** saved fields are prefilled, invalid entries are retained, and **Save and add another** supports multiple entries. Plain error dialogs also have inline messages.
- **Filters:** category, dates, and amounts work together. Start must be on or before end; minimum must be at most maximum. Equal or one-sided ranges and a zero minimum are allowed. Invalid filters show errors and no results.
- **Budgets:** current-month category limits plus monthly, yearly, and all-time overall limits belong to one wallet. Old monthly/yearly periods never carry over. Saving again updates the current limit, and overspending shows a negative remainder.
- **Dashboard:** monthly spending, six category totals, recent expenses, and monthly summaries.

Standard Django accounts keep hashed passwords and password rules. `AccountIdentity` enforces normalized, case-insensitive username/email uniqueness. Email is required and checked for format; verification and password-reset emails are not sent.

A signed add-form token lasts 24 hours. Its saved receipt prevents duplicate submissions even after deleting an expense; a fresh form permits intentionally identical entries. Edit version checks prevent overwriting newer changes from another tab. Users can access only their own records; write forms use CSRF protection.

Login and registration each allow 10 failed attempts per IP within 10 minutes. This local in-process counter resets on server restart and is not a shared production rate-limit service.

## Tests and code

```powershell
.\.venv\Scripts\python.exe manage.py test
```

The 62 regression tests cover validation, accounts, ownership, wallets, dates, filters, budgets, repeated submissions, stale edits, throttling, redirects, CSRF, and escaped HTML. They use a separate test database and leave saved app data untouched.

`app1/models.py` defines data, `forms.py` validates input, `views.py` handles requests, `urls.py` maps pages, and `tests.py` contains the tests. `templates/` holds ordinary Django pages; `website/settings.py` configures SQLite and Beirut time. Dependencies are pinned in `requirements.txt`.
