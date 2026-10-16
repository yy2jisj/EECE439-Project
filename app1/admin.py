from django.contrib import admin

from .models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ["description", "owner", "amount", "currency", "category", "date"]
    list_filter = ["currency", "category", "date"]
    search_fields = ["description"]
    readonly_fields = ["created_at"]
    exclude = ["owner"]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(owner=request.user)

    def save_model(self, request, obj, form, change):
        obj.owner = request.user
        super().save_model(request, obj, form, change)
