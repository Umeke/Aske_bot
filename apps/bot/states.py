from aiogram.fsm.state import State, StatesGroup


class ApplicationFlow(StatesGroup):
    answering = State()
    other_text = State()
    confirming = State()
