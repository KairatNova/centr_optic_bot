from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter

from sqlalchemy import select

from database.models import Person
from database.session import AsyncSessionLocal
from config import OWNER_IDS
from forms.forms_fsm import OwnerAdminsStates, OwnerMainStates
from keyboards.owner_kb import get_owner_main_keyboard
from keyboards.client_kb import get_client_keyboard

owner_admins_router = Router()

def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS

def get_admins_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить админа", callback_data="admins_add")],
        [InlineKeyboardButton(text="➖ Удалить админа", callback_data="admins_delete")],
        [InlineKeyboardButton(text="◀ Назад в главное меню", callback_data="admins_back")],
    ])

async def get_admins_list_text():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Person).where(Person.role == "admin").order_by(Person.full_name))
        admins = result.scalars().all()

    if not admins:
        return "📋 <b>Управление админами</b>\n\nАдминов пока нет."
    
    text = "📋 <b>Управление админами</b>\n\n<b>Текущие админы:</b>\n\n"
    for i, a in enumerate(admins, 1):
        text += f"{i}. 👤 {a.full_name or 'Без имени'} (@{a.username or 'нет'})\n"
        text += f"   🆔 ID: {a.telegram_id}\n"
        text += f"   📞 {a.phone or 'не указан'}\n\n"
    return text

def normalize_phone(input_str: str) -> str | None:
    digits = ''.join(filter(str.isdigit, input_str))
    
    if len(digits) == 10 and digits.startswith('0'):
        return '996' + digits[1:]
    elif len(digits) == 12 and digits.startswith('996'):
        return digits
    elif len(digits) == 13 and digits.startswith('996'):
        return digits[1:]
    return None

@owner_admins_router.callback_query(OwnerAdminsStates.admins_menu, F.data.startswith("admins_"))
async def admins_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_owner(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    action = callback.data

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    if action == "admins_add":
        await bot.send_message(
            callback.from_user.id,
            "➕ <b>Добавить админа</b>\n\n"
            "Отправьте <b>telegram_id</b> (цифры) или <b>номер телефона</b> (любым форматом: +996, 996, 0, с тире).\n"
            "Пользователь должен быть зарегистрирован в боте.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀ Отмена", callback_data="admins_cancel")]
            ])
        )
        await state.set_state(OwnerAdminsStates.waiting_for_add_input)

    elif action == "admins_delete":
        await bot.send_message(
            callback.from_user.id,
            "➖ <b>Удалить админа</b>\n\n"
            "Отправьте <b>telegram_id</b> или <b>номер телефона</b> админа.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀ Отмена", callback_data="admins_cancel")]
            ])
        )
        await state.set_state(OwnerAdminsStates.waiting_for_delete_input)

    elif action == "admins_back":
        await state.set_state(OwnerMainStates.main_menu)
        await bot.send_message(
            callback.from_user.id,
            "👑 <b>Панель владельца</b>\n\nВыберите раздел:",
            reply_markup=get_owner_main_keyboard()
        )

    await callback.answer()

# Универсальная отмена для состояний ожидания ввода (добавление/удаление)
@owner_admins_router.callback_query(StateFilter(OwnerAdminsStates.waiting_for_add_input, OwnerAdminsStates.waiting_for_delete_input), F.data == "admins_cancel")
async def cancel_add_delete(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_owner(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

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
    await callback.answer("Отменено")

# Добавление админа
@owner_admins_router.message(OwnerAdminsStates.waiting_for_add_input)
async def process_add_admin(message: Message, state: FSMContext, bot: Bot):
    if not is_owner(message.from_user.id):
        return

    input_str = message.text.strip()

    async with AsyncSessionLocal() as session:
        person = None

        if input_str.isdigit() and len(input_str) > 9:
            result = await session.execute(select(Person).where(Person.telegram_id == int(input_str)))
            person = result.scalar_one_or_none()

        if not person:
            normalized = normalize_phone(input_str)
            if normalized:
                result = await session.execute(select(Person).where(Person.phone == normalized))
                person = result.scalar_one_or_none()

        if not person:
            await message.answer("❌ Пользователь не найден.\nПроверьте telegram_id или формат телефона.")
            await bot.send_message(message.from_user.id, await get_admins_list_text(), reply_markup=get_admins_keyboard())
            await state.set_state(OwnerAdminsStates.admins_menu)
            return

        # Сохраняем имя ДО commit (пока сессия открыта)
        display_name = person.full_name or str(person.telegram_id) or person.phone or "Пользователь"

        if person.role == "owner":
            await message.answer("❌ Нельзя изменить роль владельца.")
        elif person.role == "admin":
            await message.answer(f"✅ {display_name} уже является админом.")
        else:
            person.role = "admin"
            await session.commit()
            await message.answer(f"✅ {display_name} успешно добавлен в админы!")

 
        await bot.send_message(message.from_user.id, await get_admins_list_text(), reply_markup=get_admins_keyboard())
        await state.set_state(OwnerAdminsStates.admins_menu)

# Удаление админа (аналогично)
@owner_admins_router.message(OwnerAdminsStates.waiting_for_delete_input)
async def process_delete_admin(message: Message, state: FSMContext, bot: Bot):
    if not is_owner(message.from_user.id):
        return

    input_str = message.text.strip()

    async with AsyncSessionLocal() as session:
        person = None

        if input_str.isdigit() and len(input_str) > 9:
            result = await session.execute(select(Person).where(Person.telegram_id == int(input_str)))
            person = result.scalar_one_or_none()

        if not person:
            normalized = normalize_phone(input_str)
            if normalized:
                result = await session.execute(select(Person).where(Person.phone == normalized))
                person = result.scalar_one_or_none()

        if not person:
            await message.answer("❌ Админ не найден.")
            await bot.send_message(message.from_user.id, await get_admins_list_text(), reply_markup=get_admins_keyboard())
            await state.set_state(OwnerAdminsStates.admins_menu)
            return

        display_name = person.full_name or str(person.telegram_id) or person.phone or "Пользователь"

        if person.role == "owner":
            await message.answer("❌ Нельзя удалить владельца.")
        elif person.role != "admin":
            await message.answer("❌ Этот пользователь не является админом.")
        else:
            person.role = "client"
            await session.commit()
            await message.answer(f"✅ {display_name} успешно удалён из админов.")

        await bot.send_message(message.from_user.id, await get_admins_list_text(), reply_markup=get_admins_keyboard())
        await state.set_state(OwnerAdminsStates.admins_menu)