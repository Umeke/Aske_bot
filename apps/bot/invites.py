"""Telegram-side operations: create invites, notify admins, DM applicants."""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from asgiref.sync import sync_to_async
from django.conf import settings

from apps.applications.models import Application
from apps.applications.services import (
    invite_expires_at, list_answers, mark_approved, mark_rejected,
)

from . import texts
from .keyboards import review_kb

log = logging.getLogger(__name__)


def build_bot() -> Bot:
    return Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


async def _create_invite(bot: Bot) -> str:
    link = await bot.create_chat_invite_link(
        chat_id=settings.CAST_GROUP_ID,
        member_limit=1,
        expire_date=invite_expires_at(),
    )
    return link.invite_link


async def notify_admins(bot: Bot, application: Application) -> None:
    answers = await list_answers(application.id)
    body = "\n".join(f"• <b>{q}</b>: {v}" for q, v in answers)
    header = (
        f"🆕 <b>Application #{application.id}</b>\n"
        f"From: @{application.telegram_username or application.telegram_id}\n\n"
    )
    await bot.send_message(
        chat_id=settings.ADMIN_CHAT_ID,
        text=header + body,
        reply_markup=review_kb(application.id),
    )


async def approve_application(bot: Bot, application_id: int, reviewer_id: int | None = None) -> str:
    invite_link = await _create_invite(bot)
    await mark_approved(application_id, invite_link, reviewer_id)
    return invite_link


async def send_approval_dm(bot: Bot, telegram_id: int, invite_link: str) -> None:
    await bot.send_message(
        telegram_id,
        texts.APPROVED_MESSAGE.format(link=invite_link, hours=settings.INVITE_TTL_HOURS),
        disable_web_page_preview=True,
    )


async def send_rejection_dm(bot: Bot, telegram_id: int) -> None:
    await bot.send_message(telegram_id, texts.REJECTED_MESSAGE)


_fetch_pending = sync_to_async(
    lambda ids: list(Application.objects.filter(id__in=ids, status=Application.PENDING))
)


async def approve_and_notify(application_ids: list[int], reviewer_id: int | None = None) -> int:
    """Bulk approve used by Django admin action."""
    apps = await _fetch_pending(application_ids)
    bot = build_bot()
    try:
        for app in apps:
            try:
                link = await approve_application(bot, app.id, reviewer_id)
                await send_approval_dm(bot, app.telegram_id, link)
            except Exception:
                log.exception("Approve failed for app %s", app.id)
    finally:
        await bot.session.close()
    return len(apps)


async def reject_and_notify(application_ids: list[int], reviewer_id: int | None = None) -> int:
    apps = await _fetch_pending(application_ids)
    bot = build_bot()
    try:
        for app in apps:
            try:
                await mark_rejected(app.id, reviewer_id)
                await send_rejection_dm(bot, app.telegram_id)
            except Exception:
                log.exception("Reject failed for app %s", app.id)
    finally:
        await bot.session.close()
    return len(apps)
