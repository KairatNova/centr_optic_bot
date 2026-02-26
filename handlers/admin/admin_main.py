from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from sqlalchemy import select

from database.models import Person
from database.session import AsyncSessionLocal
from config import OWNER_IDS
from forms.forms_fsm import AdminBroadcastStates, AdminClientsStates, AdminMainStates, OwnerMainStates
from keyboards.client_kb import get_client_keyboard

from utils.audit import write_audit_event

admin_main_router = Router()

def is_admin_or_owner(user_id: int) -> bool:
    # Владелец тоже может войти в админ-панель
    return user_id in OWNER_IDS

async def is_admin(user_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Person.role).where(Person.telegram_id == user_id)
        )
        role = result.scalar_one_or_none()
        return role == "admin" or role == "owner"

# Главное меню админа (Inline)
def get_admin_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Клиенты и рецепты", callback_data="admin_clients")],
        [InlineKeyboardButton(text="📨 Рассылка одному пользователю", callback_data="admin_broadcast_one")],
        [InlineKeyboardButton(text="◀ Выход из админ-панели", callback_data="admin_exit")],
    ])

@admin_main_router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if not await is_admin(user_id):
        await message.answer("❌ Доступ запрещён. У вас нет прав администратора.")
        return

    await message.answer(
        "🛠 <b>Панель администратора</b>\n\n"
        "Выберите раздел:",
        reply_markup=get_admin_main_keyboard()
    )
    await state.set_state(AdminMainStates.admin_menu)
    write_audit_event(message.from_user.id, "admin", "open_admin_panel")

@admin_main_router.callback_query(AdminMainStates.admin_menu, F.data.startswith("admin_"))
async def admin_menu_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    if not await is_admin(user_id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    action = callback.data
    write_audit_event(callback.from_user.id, "admin", "admin_menu_action", {"action": action})

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    if action == "admin_clients":
        await bot.send_message(
            callback.from_user.id,
            "🔍 <b>Поиск клиента</b>\n\n"
            "Введите номер телефона, telegram_id или часть имени/фамилии.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀ Отмена", callback_data="admin_cancel_clients")]
            ])
        )
        await state.set_state(AdminClientsStates.waiting_search_query)

    elif action == "admin_broadcast_one":
        # Запускаем поиск клиента сразу
        await bot.send_message(
            callback.from_user.id,
            "🔍 <b>Поиск клиента для отправки сообщения</b>\n\n"
            "Введите номер телефона, telegram_id или часть имени/фамилии.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀ Отмена", callback_data="admin_cancel_broadcast")]
            ])
        )
        await state.set_state(AdminBroadcastStates.waiting_search_query)

    elif action == "admin_exit":
        await state.clear()
        await bot.send_message(
            callback.from_user.id,
            "Вы вышли из панели администратора.",
            reply_markup=get_client_keyboard()  # или ваше клиентское меню
        )

    await callback.answer()