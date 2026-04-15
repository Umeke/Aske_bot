from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from apps.applications.models import Question

START_CB = "app:start"
CONFIRM_CB = "app:submit"
EDIT_CB = "app:edit"
CANCEL_CB = "app:cancel"
OPT_PREFIX = "opt:"
OTHER_VALUE = "__other__"
APPROVE_PREFIX = "adm:approve:"
REJECT_PREFIX = "adm:reject:"


def start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Start Application", callback_data=START_CB)],
    ])


def options_kb(question: Question) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=o.label, callback_data=f"{OPT_PREFIX}{o.value}")]
        for o in question.options.all()
    ]
    if question.has_other:
        rows.append([InlineKeyboardButton(text="✏ Other", callback_data=f"{OPT_PREFIX}{OTHER_VALUE}")])
    rows.append([InlineKeyboardButton(text="✖ Cancel", callback_data=CANCEL_CB)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Submit", callback_data=CONFIRM_CB),
         InlineKeyboardButton(text="✏ Edit", callback_data=EDIT_CB)],
        [InlineKeyboardButton(text="✖ Cancel", callback_data=CANCEL_CB)],
    ])


def review_kb(application_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Approve", callback_data=f"{APPROVE_PREFIX}{application_id}"),
         InlineKeyboardButton(text="❌ Reject", callback_data=f"{REJECT_PREFIX}{application_id}")],
    ])
