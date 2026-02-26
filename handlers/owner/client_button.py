from aiogram import Bot, Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from sqlalchemy import select

from database.models import BotContent
from database.session import AsyncSessionLocal
from config import OWNER_IDS, SECTION_NAMES
from forms.forms_fsm import OwnerContentStates, OwnerMainStates
from keyboards.client_kb import get_client_keyboard
from keyboards.owner_kb import get_sections_keyboard, get_owner_main_keyboard  # главное Inline-меню
from services.content import get_content, clear_content_cache

owner_content_router = Router()

def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS

# === Вход в редактирование контента из главного меню (callback из owner_main_router) ===
# Этот хендлер НЕ в этом файле, а в owner_main_router (см. ниже напоминание)
# Но здесь логика редактирования

@owner_content_router.message(OwnerContentStates.choosing_section, F.text.in_(list(SECTION_NAMES.values())))
async def section_chosen(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        await state.clear()
        return

    selected_key = next(k for k, v in SECTION_NAMES.items() if v == message.text)
    current_text = await get_content(selected_key, default="Текст не задан")

    await state.update_data(edit_key=selected_key)

    await message.answer(
        f"<b>Текущий текст: «{message.text}»</b>\n\n"
        f"{current_text}\n\n"
        "Отправьте новый текст (HTML-разметка поддерживается).\n"
        "Или нажмите «◀ Выйти из панели» для отмены.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀ Выйти из панели")]],
            resize_keyboard=True
        )
    )
    await state.set_state(OwnerContentStates.waiting_new_text)

@owner_content_router.message(OwnerContentStates.waiting_new_text, F.text)
async def process_edit_or_cancel(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        await state.clear()
        return

    if message.text == "◀ Выйти из панели":
        await message.answer(
            "❌ Редактирование отменено.\n\nВыберите другой раздел:",
            reply_markup=get_sections_keyboard()
        )
        await state.set_state(OwnerContentStates.choosing_section)
        return

    # Сохранение нового текста
    data = await state.get_data()
    edit_key = data["edit_key"]
    new_text = message.text.strip()

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(BotContent).where(BotContent.key == edit_key))
        row = result.scalar_one_or_none()

        if row:
            row.value = new_text
        else:
            row = BotContent(key=edit_key, value=new_text)
            session.add(row)

        await session.commit()

    clear_content_cache()

    section_name = SECTION_NAMES.get(edit_key, edit_key)
    await message.answer(
        f"✅ Текст «{section_name}» обновлён!\n\nВыберите следующий раздел:",
        reply_markup=get_sections_keyboard()
    )
    await state.set_state(OwnerContentStates.choosing_section)

# ... ваш код section_chosen и process_edit_or_cancel без изменений ...

# Выход из меню выбора разделов — возврат в главное Inline-меню
@owner_content_router.message(OwnerContentStates.choosing_section, F.text == "◀ Выйти из панели")
async def exit_from_content_edit(message: Message, state: FSMContext, bot: Bot):
    if not is_owner(message.from_user.id):
        return

    # Скрываем ReplyKeyboard с разделами
    await message.answer("Вы вышли из редактирования контента.", reply_markup=ReplyKeyboardRemove())

    # Возвращаем главное Inline-меню владельца
    await bot.send_message(
        message.from_user.id,
        "👑 <b>Панель владельца</b>\n\nВыберите раздел:",
        reply_markup=get_owner_main_keyboard()
    )
    await state.set_state(OwnerMainStates.main_menu)  # важный переход состояния!

# Универсальный полный выход (если кнопка нажата в любом состоянии редактирования)
@owner_content_router.message(F.text == "◀ Выйти из панели")
async def full_exit_from_content(message: Message, state: FSMContext, bot: Bot):
    if not is_owner(message.from_user.id):
        return

    await state.clear()
    await message.answer("Вы вышли из панели владельца.", reply_markup=ReplyKeyboardRemove())
    #await bot.send_message(message.from_user.id, "Главное меню:", reply_markup=get_client_keyboard())

# Защита от случайных сообщений
@owner_content_router.message(OwnerContentStates.choosing_section)
async def unknown_choosing(message: Message):
    if is_owner(message.from_user.id):
        await message.answer("Выберите раздел из списка ниже.", reply_markup=get_sections_keyboard())

@owner_content_router.message(OwnerContentStates.waiting_new_text)
async def unknown_waiting(message: Message):
    if is_owner(message.from_user.id):
        await message.answer("Отправьте новый текст или нажмите «◀ Выйти из панели».", reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀ Выйти из панели")]], resize_keyboard=True
        ))