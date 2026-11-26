from django.urls import path

from . import views


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("register/", views.register, name="register"),
    path("login/", views.login_user, name="login"),
    path("logout/", views.logout_user, name="logout"),
    path("profile/", views.profile, name="profile"),
    path("expenses/", views.default_history, name="default_history"),
    path("expenses/add/", views.default_add, name="default_add"),
    path("expenses/<int:expense_id>/edit/", views.edit_expense, name="edit_expense"),
    path("expenses/<int:expense_id>/delete/", views.delete_expense, name="delete_expense"),
    path("expenses/<str:currency>/", views.expense_history, name="expense_history"),
    path("expenses/<str:currency>/add/", views.add_expense, name="add_expense"),
    path("expenses/<str:currency>/budget/", views.save_budget, name="save_budget"),
    path("expenses/<str:currency>/overall-budget/", views.save_overall_budget, name="save_overall_budget"),
    path("budgets/<int:budget_id>/delete/", views.delete_budget, name="delete_budget"),
    path("overall-budgets/<int:budget_id>/delete/", views.delete_overall_budget, name="delete_overall_budget"),
]
