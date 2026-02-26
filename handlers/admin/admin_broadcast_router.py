from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from sqlalchemy import select, or_

from database.models import Person, Vision
from database.session import AsyncSessionLocal
from config import OWNER_IDS
from forms.forms_fsm import AdminMainStates, AdminBroadcastStates
from handlers.owner.crud.clients_router import show_client_profile
from keyboards.admin_kb import get_admin_main_keyboard  # если клавиатура админа отдельная

admin_broadcast_router = Router()



async def has_admin_access(user_id: int) -> bool:
    """
    Проверяет, имеет ли пользователь права администратора или владельца.
    - Если user_id в OWNER_IDS → доступ есть (даже если role не "owner").
    - Если role в БД == "admin" или "owner" → доступ есть.
    """
    if user_id in OWNER_IDS:
        return True

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Person.role).where(Person.telegram_id == user_id)
        )
        role = result.scalar_one_or_none()
        return role in ("admin", "owner")

def normalize_phone(input_str: str) -> str | None:
    digits = ''.join(filter(str.isdigit, input_str))
    if len(digits) == 10 and digits.startswith('0'):
        return '996' + digits[1:]
    elif len(digits) == 12 and digits.startswith('996'):
        return digits
    return None

@admin_broadcast_router.callback_query(AdminMainStates.admin_menu, F.data == "admin_broadcast_one")
async def start_broadcast_one(callback: CallbackQuery, message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id

    if not await has_admin_access(user_id):
        await message.answer("❌ Доступ запрещён.")
        await state.clear()
        return

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    await bot.send_message(
        callback.from_user.id,
        "🔍 <b>Поиск клиента для сообщения</b>\n\n"
        "Введите номер телефона, telegram_id или часть имени/фамилии.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Отмена", callback_data="admin_cancel_broadcast")]
        ])
    )
    await state.set_state(AdminBroadcastStates.waiting_search_query)
    await callback.answer()

# Отмена поиска
@admin_broadcast_router.callback_query(AdminBroadcastStates.waiting_search_query, F.data == "admin_cancel_broadcast")
async def cancel_broadcast(callback: CallbackQuery, message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id

    if not await has_admin_access(user_id):
        await message.answer("❌ Доступ запрещён.")
        await state.clear()
        return


    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    await bot.send_message(
        callback.from_user.id,
        "🛠 <b>Панель администратора</b>\n\nВыберите раздел:",
        reply_markup=get_admin_main_keyboard()
    )
    await state.set_state(AdminMainStates.admin_menu)
    await callback.answer("Отменено")

# Поиск клиента
@admin_broadcast_router.message(AdminBroadcastStates.waiting_search_query)
async def process_search(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id

    if not await has_admin_access(user_id):
        await message.answer("❌ Доступ запрещён.")
        await state.clear()
        return

    query = message.text.strip()

    if not query:
        await message.answer("Введите запрос для поиска.")
        return

    async with AsyncSessionLocal() as session:
        conditions = []

        # По telegram_id
        if query.isdigit() and len(query) > 8:  # telegram_id обычно длиннее
            conditions.append(Person.telegram_id == int(query))

        # По телефону
        normalized = normalize_phone(query)
        if normalized:
            conditions.append(Person.phone == normalized)

        # По имени/фамилии
        if query:
            conditions.append(or_(
                Person.first_name.ilike(f"%{query}%"),
                Person.last_name.ilike(f"%{query}%"),
                Person.full_name.ilike(f"%{query}%")
            ))

        result = await session.execute(
            select(Person).where(or_(*conditions)).limit(15)
        )
        persons = result.scalars().all()

    if not persons:
        await message.answer(
            "❌ Клиент не найден. Попробуйте другой запрос.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀ Отмена", callback_data="admin_cancel_broadcast")]
            ])
        )
        return

    if len(persons) == 1:
        await show_profile(message, persons[0], state, bot)
        return

    # Несколько совпадений — список
    kb = []
    for p in persons:
        name = p.full_name or p.phone or str(p.telegram_id)
        kb.append([InlineKeyboardButton(text=name, callback_data=f"admin_profile_{p.id}")])

    kb.append([InlineKeyboardButton(text="◀ Отмена", callback_data="admin_cancel_broadcast")])

    await message.answer(
        f"🔍 Найдено {len(persons)} клиентов. Выберите:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )
# Показ профиля клиента
async def show_profile(trigger, person: Person, state: FSMContext, bot: Bot):
    async with AsyncSessionLocal() as session:
        last_vision = await session.execute(
            select(Vision)
            .where(Vision.person_id == person.id)
            .order_by(Vision.visit_date.desc())
            .limit(1)
        )
        last_vision = last_vision.scalar_one_or_none()

    profile_text = f"👤 <b>Профиль клиента</b>\n\n"
    profile_text += f"ФИО: {person.full_name or '—'}\n"
    profile_text += f"Возраст: {person.age or '—'}\n"
    profile_text += f"Телефон: {person.phone or '—'}\n"
    profile_text += f"Telegram ID: {person.telegram_id or '—'}\n"
    profile_text += f"Роль: {person.role}\n"
    profile_text += f"Дата регистрации: {person.created_at.date() if person.created_at else '—'}\n"
    profile_text += f"Последний визит: {person.last_visit_date or '—'}\n\n"

    if last_vision:
        profile_text += "<b>Последняя запись зрения:</b>\n"
        profile_text += f"Дата: {last_vision.visit_date}\n"
        profile_text += f"Правая: SPH {last_vision.sph_r or '—'} | CYL {last_vision.cyl_r or '—'} | AXIS {last_vision.axis_r or '—'}\n"
        profile_text += f"Левая: SPH {last_vision.sph_l or '—'} | CYL {last_vision.cyl_l or '—'} | AXIS {last_vision.axis_l or '—'}\n"
        profile_text += f"PD: {last_vision.pd or '—'}\n"
        if last_vision.note:
            profile_text += f"Примечание: {last_vision.note}\n"
    else:
        profile_text += "<i>Записей зрения пока нет</i>\n"

    kb = [
        [InlineKeyboardButton(text="📨 Отправить сообщение", callback_data=f"admin_send_msg_{person.id}")],
        [InlineKeyboardButton(text="◀ Назад к поиску", callback_data="admin_back_to_search")],
        [InlineKeyboardButton(text="◀ В админ-меню", callback_data="admin_back_to_menu")],
    ]

    if isinstance(trigger, Message):
        await trigger.answer(profile_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await trigger.message.edit_text(profile_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

    await state.update_data(person_id=person.id)
    await state.set_state(AdminBroadcastStates.viewing_profile)

# Выбор профиля из списка
@admin_broadcast_router.callback_query(F.data.startswith("admin_profile_"))
async def select_profile(callback: CallbackQuery, state: FSMContext, bot: Bot):
    person_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        person = await session.get(Person, person_id)
    if person:
        await show_client_profile(callback, person, state, bot)  # ← callback как trigger
    await callback.answer()

# Начать отправку сообщения
@admin_broadcast_router.callback_query(AdminBroadcastStates.viewing_profile, F.data.startswith("admin_send_msg_"))
async def start_send_message(callback: CallbackQuery, state: FSMContext, bot: Bot):
    person_id = int(callback.data.split("_")[3])
    await state.update_data(person_id=person_id)

    await bot.send_message(
        callback.from_user.id,
        "📨 Введите текст сообщения для отправки клиенту:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Отмена", callback_data="admin_cancel_send")]
        ])
    )
    await state.set_state(AdminBroadcastStates.waiting_message_text)
    await callback.answer()

# Отмена отправки
@admin_broadcast_router.callback_query(F.data == "admin_cancel_send")
async def cancel_send(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    person_id = data.get("person_id")

    if person_id:
        async with AsyncSessionLocal() as session:
            person = await session.get(Person, person_id)
        if person:
            await show_profile(callback, person, state, bot)

    await callback.answer("Отправка отменена")

# Обработка текста сообщения
@admin_broadcast_router.message(AdminBroadcastStates.waiting_message_text)
async def send_message_to_client(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    person_id = data.get("person_id")

    async with AsyncSessionLocal() as session:
        person = await session.get(Person, person_id)

    if not person or not person.telegram_id:
        await message.answer("❌ Ошибка: клиент не найден или нет Telegram ID.")
        await state.set_state(AdminMainStates.admin_menu)
        return

    try:
        await bot.send_message(person.telegram_id, message.text)
        await message.answer(f"✅ Сообщение отправлено клиенту {person.full_name or person.telegram_id}!")
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки: {str(e)}")

    # Возврат в профиль
    await show_profile(message, person, state, bot)
    await state.set_state(AdminBroadcastStates.viewing_profile)

# Назад к поиску из профиля
@admin_broadcast_router.callback_query(AdminBroadcastStates.viewing_profile, F.data == "admin_back_to_search")
async def admin_back_to_search(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await bot.send_message(
        callback.from_user.id,
        "🔍 <b>Поиск клиента для сообщения</b>\n\n"
        "Введите номер телефона, telegram_id или часть имени/фамилии.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Отмена", callback_data="admin_cancel_broadcast")]
        ])
    )
    await state.set_state(AdminBroadcastStates.waiting_search_query)
    await callback.answer()

# Возврат в админ-меню
@admin_broadcast_router.callback_query(F.data == "admin_back_to_menu")
async def admin_back_to_menu(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await bot.send_message(
        callback.from_user.id,
        "🛠 <b>Панель администратора</b>\n\nВыберите раздел:",
        reply_markup=get_admin_main_keyboard()
    )
    await state.set_state(AdminMainStates.admin_menu)
    await callback.answer()