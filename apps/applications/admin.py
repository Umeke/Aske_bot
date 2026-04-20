import asyncio

from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import Answer, Application, Question, QuestionOption


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 1
    fields = ("order", "value", "label", "is_active")

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("order", "code", "question_type", "is_active", "has_other")
    list_editable = ("is_active",)
    list_filter = ("question_type", "is_active")
    search_fields = ("code", "text")
    inlines = [QuestionOptionInline]


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    readonly_fields = ("question", "value")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("id", "display_name", "telegram_username", "status", "submitted_at", "joined_group")
    list_filter = ("status", "joined_group", "submitted_at")
    search_fields = ("telegram_username", "telegram_id", "answers__value")
    readonly_fields = (
        "telegram_id", "telegram_username", "submitted_at", "reviewed_at",
        "reviewed_by", "invite_link", "joined_group", "answers_table",
    )
    fieldsets = (
        ("Telegram", {"fields": ("telegram_id", "telegram_username")}),
        ("Review", {"fields": ("status", "reviewed_at", "reviewed_by", "invite_link", "joined_group")}),
        ("Answers", {"fields": ("answers_table",)}),
    )
    inlines = [AnswerInline]
    actions = ("approve_selected", "reject_selected")

    @admin.display(description="Answers")
    def answers_table(self, obj: Application):
        rows = "".join(
            f"<tr><td><b>{a.question.text}</b></td><td>{a.value}</td></tr>"
            for a in obj.answers.select_related("question").order_by("question__order")
        )
        return mark_safe(f"<table style='width:100%'>{rows}</table>") if rows else "—"

    @admin.action(description="Approve selected (send invite)")
    def approve_selected(self, request, queryset):
        from apps.bot.invites import approve_and_notify

        pending = queryset.filter(status=Application.PENDING)
        count = asyncio.run(approve_and_notify([a.id for a in pending], reviewer_id=request.user.id))
        messages.success(request, f"Approved {count} application(s)")

    @admin.action(description="Reject selected")
    def reject_selected(self, request, queryset):
        from apps.bot.invites import reject_and_notify

        pending = queryset.filter(status=Application.PENDING)
        count = asyncio.run(reject_and_notify([a.id for a in pending], reviewer_id=request.user.id))
        messages.success(request, f"Rejected {count} application(s)")
