"""Business logic for application lifecycle.

Kept separate from models and handlers so the same flow works from
bot callbacks, Django admin actions, and tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

from .models import Answer, Application, Question


@dataclass
class SubmittedAnswer:
    code: str
    value: str


@sync_to_async
def get_active_questions() -> list[Question]:
    return list(Question.objects.filter(is_active=True).prefetch_related("options"))


@sync_to_async
def get_application(telegram_id: int) -> Application | None:
    return Application.objects.filter(telegram_id=telegram_id).first()


@sync_to_async
def create_application(
    telegram_id: int, username: str, answers: list[SubmittedAnswer]
) -> Application:
    questions = {q.code: q for q in Question.objects.filter(is_active=True)}
    app, _ = Application.objects.update_or_create(
        telegram_id=telegram_id,
        defaults={"telegram_username": username, "status": Application.PENDING},
    )
    app.answers.all().delete()
    Answer.objects.bulk_create([
        Answer(application=app, question=questions[a.code], value=a.value)
        for a in answers if a.code in questions
    ])
    return app


@sync_to_async
def list_answers(application_id: int) -> list[tuple[str, str]]:
    qs = Answer.objects.filter(application_id=application_id).select_related("question")
    return [(a.question.text, a.value) for a in qs.order_by("question__order")]


@sync_to_async
def mark_approved(application_id: int, invite_link: str, reviewer_id: int | None = None) -> None:
    Application.objects.filter(pk=application_id).update(
        status=Application.APPROVED,
        invite_link=invite_link,
        reviewed_at=timezone.now(),
        reviewed_by_id=reviewer_id,
    )


@sync_to_async
def mark_rejected(application_id: int, reviewer_id: int | None = None) -> None:
    Application.objects.filter(pk=application_id).update(
        status=Application.REJECTED,
        reviewed_at=timezone.now(),
        reviewed_by_id=reviewer_id,
    )


@sync_to_async
def mark_joined(telegram_id: int) -> Application | None:
    """Return the application only on first join; None for rejoins."""
    app = Application.objects.filter(telegram_id=telegram_id).first()
    if not app or app.joined_group:
        return None
    app.joined_group = True
    app.save(update_fields=["joined_group"])
    return app


def invite_expires_at():
    return timezone.now() + timedelta(hours=settings.INVITE_TTL_HOURS)
