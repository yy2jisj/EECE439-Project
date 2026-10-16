# Understanding PocketManager

## The main idea

A browser sends a request to Django. A URL selects a view function. That view
checks the current account, reads or saves information through a model, and gives
data to an HTML template. The template produces the page the browser displays.

For example, submitting **Add expense** sends a POST request to the add view.
The view checks the form. If it is valid, it assigns the logged-in user as the
owner, saves the expense, and redirects to history. If it is invalid, it renders
the same form with useful error messages.

## Models: what the database stores

`app1/models.py` defines `Expense`. Each row is one expense, with a description,
decimal amount, category, currency, expense date, creation timestamp, and owner.
The owner is a foreign key to Django's existing user model: one user can own many
expenses. Deleting a user also removes that user's expenses through the cascade
relationship. The tracker does not need a second profile table because the basic
profile information already exists on the user.

The six categories and the two currencies are fixed choices. Using a choices list
is simpler here than giving users a separate category-management page. Decimal
money avoids the rounding errors that binary floating-point numbers can introduce.
Form validation catches invalid values before saving; database constraints also
reject nonpositive amounts and unsupported categories/currencies.

Migrations describe database changes. Historical migrations `0001` through `0007`
come from the student/course template. New migration `0008` removes those models
and creates `Expense`. A fresh `migrate` runs the whole chain in order, leaving
only the final expense schema along with Django's own tables.

## Forms: checking user input

`app1/forms.py` contains:

- `RegistrationForm`: extends Django's user-creation form with optional account
  information. Django handles password confirmation, strength checks, and hashing.
- `ExpenseForm`: a ModelForm listing only editable expense fields. It deliberately
  excludes the owner so a submitted owner ID cannot choose another account.
- `ExpenseFilterForm`: ordinary optional fields for category and date/amount
  ranges. It checks that a range's start is not greater than its end.

Django's `AuthenticationForm` validates login credentials. In each template, the
shared form-field include renders labels, input widgets, help text, and errors.

## Views: deciding what happens

`app1/views.py` uses ordinary function-based views. Account views register, log
in, log out, and show the profile. Expense views list, add, edit, and delete rows.
The dashboard view calculates totals from saved records rather than using example
numbers. The currency view stores a valid selected currency in the user's session.

The key privacy rule is `owner=request.user`. History and dashboard queries use
this restriction. Editing and deletion also use it inside `get_object_or_404`.
If someone types another user's expense ID into a URL, the lookup returns 404.
Hiding a link alone would not protect the expense; the server-side lookup does.

Expense forms use `save(commit=False)` when a new owner must be assigned before
the database save. A successful POST redirects so refreshing the resulting page
does not submit the same new expense again. Logout and currency changes accept
POST only. GET requests display information and deletion confirmation.

The dashboard first selects the user's expenses in the active currency. It sums
the current month's records, groups category amounts for that month, takes recent
records, and groups all recorded months for the summary. Missing totals become
decimal zero. USD and LBP are never added together.

## URLs: connecting page addresses to views

`website/urls.py` includes `app1/urls.py`. The application's URL file connects
paths such as `/expenses/add/` to view functions and gives them names such as
`expense_add`. Templates use `{% url 'expense_add' %}` instead of hardcoding the
address. This keeps links consistent when a route changes.

## Templates and CSS: what the user sees

`templates/base.html` provides the document structure, navigation, messages,
currency switch, and stylesheet link. Each page extends this base and supplies
its main content. This avoids copying navigation into every file. Templates loop
over expenses and summary rows and escape user descriptions automatically.

`app1/static/app1/style.css` contains only the basic layout, forms, tables, and
small-screen rules. There is no frontend framework or JavaScript dependency.

`app1/context_processors.py` supplies the app name and selected currency to all
templates. Django's messages framework carries success messages across redirects.
CSRF tokens inside POST forms let Django reject submissions missing a valid token.

## Other files

- `website/settings.py`: installed apps, middleware, templates, database,
  timezone, static files, and local configuration defaults.
- `app1/admin.py`: optional expense visibility in Django administration.
- `app1/management/commands/seed_demo.py`: optional, clearly fictional examples
  for an existing account; no automatic demo account or password.
- `app1/tests.py`: important account, expense, ownership, filter, and calculation
  behavior checked using test users and a separate test database.
- `manage.py`: entry point for running the server, migrations, checks, and tests.

To explain the project, follow one expense from its URL to the view, through the
form and model, and then into the history template. That path shows how the parts
work together without needing to memorize every line.
