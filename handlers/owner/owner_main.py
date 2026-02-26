from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from config import OWNER_IDS
from forms.forms_fsm import (OwnerAdminsStates, OwnerBroadcastStates, 
                             OwnerClientsStates, OwnerContentStates, OwnerExportStates, OwnerMainStates
                              )

from handlers.owner.admins_router import get_admins_keyboard, get_admins_list_text
from keyboards.client_kb import get_client_keyboard
from keyboards.owner_kb import get_admins_submenu_keyboard, get_broadcast_submenu_keyboard, get_clients_submenu_keyboard, get_dev_panel_keyboard, get_export_submenu_keyboard, get_owner_main_keyboard, get_sections_keyboard
from services.content import get_content
from utils.audit import write_audit_event

owner_main_router = Router()

def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS

@owner_main_router.message(Command("owner"))
async def cmd_owner_main(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return

    await message.answer(
        "👑 <b>Панель владельца</b>\n\n"
        "Выберите нужный раздел:",
        reply_markup=get_owner_main_keyboard()
    )
    await state.set_state(OwnerMainStates.main_menu)
    write_audit_event(message.from_user.id, "owner", "open_owner_panel")

@owner_main_router.callback_query(OwnerMainStates.main_menu, F.data.startswith("owner_"))
async def owner_menu_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_owner(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    action = callback.data
    write_audit_event(callback.from_user.id, "owner", "owner_menu_action", {"action": action})

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    if action == "owner_edit_content":
        await bot.send_message(
            callback.from_user.id,
            "📝 <b>Редактирование контента бота</b>\n\nВыберите раздел:",
            reply_markup=get_sections_keyboard()
        )
        await state.set_state(OwnerContentStates.choosing_section)  # переход в состояние редактирования

    elif action == "owner_dev_panel":
        await bot.send_message(
            callback.from_user.id,
            "🛠 <b>Панель разработчика</b>\n\nВыберите действие:",
            reply_markup=get_dev_panel_keyboard()
        )
        
    elif action == "owner_clients":
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        await bot.send_message(
            callback.from_user.id,
            "🔍 <b>Поиск клиента</b>\n\n"
            "Введите номер телефона, telegram_id или часть имени/фамилии.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀ Отмена", callback_data="clients_cancel_search")]
            ])
        )
        await state.set_state(OwnerClientsStates.waiting_search_query)

    elif action == "owner_broadcast":
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        await bot.send_message(
            callback.from_user.id,
            "📨 <b>Рассылки</b>\n\nВыберите действие:",
            reply_markup=get_broadcast_submenu_keyboard()  # новая клавиатура, см. ниже
        )
        await state.set_state(OwnerBroadcastStates.broadcast_menu)

    elif action == "owner_exports":
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        await bot.send_message(
            callback.from_user.id,
            "📊 <b>Выгрузки данных</b>\n\nВыберите тип выгрузки:",
            reply_markup=get_export_submenu_keyboard()
        )
        await state.set_state(OwnerExportStates.export_menu)

    elif action == "owner_manage_admins":
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        await bot.send_message(
            callback.from_user.id,
            await get_admins_list_text(),
            reply_markup=get_admins_keyboard()
        )
        await state.set_state(OwnerAdminsStates.admins_menu)

    elif action == "owner_exit":
        await state.clear()
        await bot.send_message(
            callback.from_user.id,
            "Вы вышли из панели владельца.",
            reply_markup=get_client_keyboard()
        )

    await callback.answer()

@owner_main_router.message(OwnerMainStates.main_menu)
async def unknown_in_main_menu(message: Message):
    if is_owner(message.from_user.id):
        await message.answer("Пожалуйста, используйте кнопки 👇", reply_markup=get_owner_main_keyboard())