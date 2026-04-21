"""Telegram handlers.

Routers are split by responsibility:
    user_router  - /start, application FSM, confirmation
    admin_router - approve/reject callbacks from the admin chat
    group_router - welcome on join
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery, ChatMemberUpdated, InlineKeyboardButton,
    InlineKeyboardMarkup, Message,
)
from asgiref.sync import sync_to_async
from django.conf import settings

from apps.applications.models import Application, Question
from apps.applications.services import (
    SubmittedAnswer, create_application, get_active_questions,
    get_application, mark_joined, mark_rejected,
)

from . import texts
from .invites import (
    approve_application, notify_admins, send_approval_dm,
    send_rejection_dm,
)
from .keyboards import (
    APPROVE_PREFIX, CANCEL_CB, CONFIRM_CB, EDIT_CB, OPT_PREFIX,
    OTHER_VALUE, REJECT_PREFIX, START_CB,
    confirm_kb, start_kb,
)
from .states import ApplicationFlow

log = logging.getLogger(__name__)

user_router = Router(name="user")
admin_router = Router(name="admin")
group_router = Router(name="group")


# ---------- FSM snapshot types ----------

@dataclass
class QOption:
    value: str
    label: str


@dataclass
class QSnapshot:
    code: str
    text: str
    question_type: str
    has_other: bool
    options: list[QOption]


def _snapshot(questions: list[Question]) -> list[dict]:
    return [
        asdict(QSnapshot(
            code=q.code, text=q.text, question_type=q.question_type,
            has_other=q.has_other,
            options=[QOption(value=o.value, label=o.label) for o in q.options.all()],
        ))
        for q in questions
    ]


# ---------- helpers ----------

async def _ask(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    questions: list[dict] = data["questions"]
    idx: int = data["idx"]

    if idx >= len(questions):
        await _show_summary(message, state)
        return

    q = questions[idx]
    prefix = f"📝 Step {idx + 1}/{len(questions)}\n\n"
    text = prefix + q["text"]

    if q["question_type"] == Question.CHOICE:
        kb = _options_kb_from_dict(q)
        await message.answer(text, reply_markup=kb)
    else:
        await message.answer(text)

    await state.set_state(ApplicationFlow.answering)


def _options_kb_from_dict(q: dict) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=o["label"], callback_data=f"{OPT_PREFIX}{o['value']}")]
        for o in q["options"]
    ]
    if q["has_other"]:
        rows.append([InlineKeyboardButton(text="✏ Other", callback_data=f"{OPT_PREFIX}{OTHER_VALUE}")])
    rows.append([InlineKeyboardButton(text="✖ Cancel", callback_data=CANCEL_CB)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _store_and_advance(message: Message, state: FSMContext, value: str) -> None:
    data = await state.get_data()
    questions = data["questions"]
    idx = data["idx"]
    answers = data["answers"]
    answers[questions[idx]["code"]] = value
    await state.update_data(answers=answers, idx=idx + 1)
    await _ask(message, state)


async def _show_summary(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lines = [
        f"• <b>{q['text']}</b>\n  → {data['answers'].get(q['code'], '—')}"
        for q in data["questions"]
    ]
    body = f"{texts.CONFIRM_HEADER}\n\n" + "\n\n".join(lines) + f"\n\n{texts.CONFIRM_FOOTER}"
    await message.answer(body, reply_markup=confirm_kb())
    await state.set_state(ApplicationFlow.confirming)


# ---------- user flow ----------

@user_router.message(CommandStart())
async def on_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    existing = await get_application(message.from_user.id)
    if existing and existing.status == Application.APPROVED:
        await message.answer(texts.ALREADY_APPROVED)
        return
    if existing and existing.status == Application.PENDING:
        await message.answer(texts.ALREADY_PENDING)
        return
    await message.answer(texts.WELCOME, reply_markup=start_kb())


@user_router.message(Command("cancel"))
async def on_cancel_cmd(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.CANCELLED)


@user_router.callback_query(F.data == CANCEL_CB)
async def on_cancel_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer(texts.CANCELLED)
    await callback.answer()


@user_router.callback_query(F.data == START_CB)
async def on_start_application(callback: CallbackQuery, state: FSMContext) -> None:
    questions = await get_active_questions()
    if not questions:
        await callback.answer("Application is not configured yet.", show_alert=True)
        return
    await state.update_data(questions=_snapshot(questions), idx=0, answers={})
    await callback.answer()
    await _ask(callback.message, state)


@user_router.message(ApplicationFlow.answering, F.text)
async def on_text_answer(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    q = data["questions"][data["idx"]]
    if q["question_type"] == Question.CHOICE:
        await message.answer("Please tap one of the buttons above.")
        return
    await _store_and_advance(message, state, message.text.strip())


@user_router.callback_query(ApplicationFlow.answering, F.data.startswith(OPT_PREFIX))
async def on_option_pick(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data[len(OPT_PREFIX):]
    await callback.answer()
    if value == OTHER_VALUE:
        await callback.message.answer("Please type your answer:")
        await state.set_state(ApplicationFlow.other_text)
        return
    data = await state.get_data()
    q = data["questions"][data["idx"]]
    label = next((o["label"] for o in q["options"] if o["value"] == value), value)
    await _store_and_advance(callback.message, state, label)


@user_router.message(ApplicationFlow.other_text, F.text)
async def on_other_text(message: Message, state: FSMContext) -> None:
    await _store_and_advance(message, state, f"Other: {message.text.strip()}")


@user_router.callback_query(ApplicationFlow.confirming, F.data == EDIT_CB)
async def on_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(idx=0, answers={})
    await callback.answer("Restarting")
    await _ask(callback.message, state)


@user_router.callback_query(ApplicationFlow.confirming, F.data == CONFIRM_CB)
async def on_submit(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    user = callback.from_user
    answers = [SubmittedAnswer(code=code, value=val) for code, val in data["answers"].items()]
    application = await create_application(user.id, user.username or "", answers)
    await state.clear()
    await callback.message.answer(texts.SUBMITTED)
    await callback.answer()
    try:
        await notify_admins(callback.bot, application)
    except Exception:
        log.exception("Failed to notify admins for app %s", application.id)


# ---------- admin flow ----------


@sync_to_async
def _get_application(pk: int) -> Application | None:
    return Application.objects.filter(pk=pk).first()


@admin_router.callback_query(F.data.startswith(APPROVE_PREFIX))
async def on_approve(callback: CallbackQuery) -> None:
    if callback.message.chat.id != settings.ADMIN_CHAT_ID:
        await callback.answer("Not allowed", show_alert=True)
        return
    app_id = int(callback.data[len(APPROVE_PREFIX):])
    app = await _get_application(app_id)
    if not app or app.status != Application.PENDING:
        await callback.answer("Already processed")
        await _strike(callback)
        return
    invite_link = await approve_application(callback.bot, app_id)
    await send_approval_dm(callback.bot, app.telegram_id, invite_link)
    await callback.message.edit_text(callback.message.html_text + "\n\n✅ Approved")
    await callback.answer("Approved & invite sent")


@admin_router.callback_query(F.data.startswith(REJECT_PREFIX))
async def on_reject(callback: CallbackQuery) -> None:
    if callback.message.chat.id != settings.ADMIN_CHAT_ID:
        await callback.answer("Not allowed", show_alert=True)
        return
    app_id = int(callback.data[len(REJECT_PREFIX):])
    app = await _get_application(app_id)
    if not app or app.status != Application.PENDING:
        await callback.answer("Already processed")
        await _strike(callback)
        return
    await mark_rejected(app_id)
    await send_rejection_dm(callback.bot, app.telegram_id)
    await callback.message.edit_text(callback.message.html_text + "\n\n❌ Rejected")
    await callback.answer("Rejected")


async def _strike(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        log.debug("Could not strike buttons", exc_info=True)


# ---------- group flow ----------

@group_router.chat_member()
async def on_member_update(event: ChatMemberUpdated) -> None:
    if event.chat.id != settings.CAST_GROUP_ID:
        return
    if event.new_chat_member.status not in ("member", "administrator"):
        return
    user = event.new_chat_member.user
    app = await mark_joined(user.id)
    if app is None:
        return
    mention = f"@{user.username}" if user.username else user.mention_html(user.full_name)
    thread_id = settings.CAST_INTRODUCTIONS_TOPIC_ID or None
    await event.bot.send_message(
        chat_id=settings.CAST_GROUP_ID,
        text=texts.WELCOME_IN_GROUP.format(mention=mention),
        message_thread_id=thread_id,
    )
    await event.bot.send_message(
        chat_id=settings.CAST_GROUP_ID,
        text=texts.RULES_REMINDER,
        message_thread_id=thread_id,
    )
