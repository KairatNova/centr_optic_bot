# Новый файл: routers/admin_clients_router.py

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from sqlalchemy import select, or_

from database.models import Person, Vision
from database.session import AsyncSessionLocal
from config import OWNER_IDS
from forms.forms_fsm import AdminClientsStates, AdminMainStates
from keyboards.admin_kb import get_admin_main_keyboard

admin_clients_router = Router()

async def has_admin_access(user_id: int) -> bool:
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

@admin_clients_router.callback_query(AdminMainStates.admin_menu, F.data == "admin_clients")
async def start_clients_search(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await has_admin_access(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    await bot.send_message(
        callback.from_user.id,
        "🔍 <b>Поиск клиента</b>\n\n"
        "Введите номер телефона, telegram_id или часть имени/фамилии.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Отмена", callback_data="admin_clients_cancel")]
        ])
    )
    await state.set_state(AdminClientsStates.waiting_search_query)
    await callback.answer()

# Отмена поиска — возврат в админ-меню
@admin_clients_router.callback_query(AdminClientsStates.waiting_search_query, F.data == "admin_clients_cancel")
async def cancel_search(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await has_admin_access(callback.from_user.id):
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
    await callback.answer("Поиск отменён")

# Поиск клиента
@admin_clients_router.message(AdminClientsStates.waiting_search_query)
async def process_search(message: Message, state: FSMContext, bot: Bot):
    if not await has_admin_access(message.from_user.id):
        await message.answer("❌ Доступ запрещён.")
        await state.clear()
        return

    query = message.text.strip()

    async with AsyncSessionLocal() as session:
        conditions = []

        if query.isdigit():
            conditions.append(Person.telegram_id == int(query))

        normalized = normalize_phone(query)
        if normalized:
            conditions.append(Person.phone == normalized)

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
            "❌ Клиенты не найдены. Попробуйте другой запрос.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀ Отмена", callback_data="admin_clients_cancel")]
            ])
        )
        return

    if len(persons) == 1:
        await admin_show_profile(message, persons[0], state, bot)
        return

    kb = []
    for p in persons:
        name = p.full_name or p.phone or str(p.telegram_id)
        kb.append([InlineKeyboardButton(text=name, callback_data=f"admin_client_profile_{p.id}")])

    kb.append([InlineKeyboardButton(text="◀ Отмена", callback_data="admin_clients_cancel")])

    await message.answer(
        f"🔍 Найдено {len(persons)} клиентов. Выберите:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

# Показ профиля клиента (краткий формат + ваши кнопки)
async def admin_show_profile(trigger, person: Person, state: FSMContext, bot: Bot):
    async with AsyncSessionLocal() as session:
        last_vision = await session.execute(
            select(Vision)
            .where(Vision.person_id == person.id)
            .order_by(Vision.visit_date.desc())
            .limit(1)
        )
        last_vision = last_vision.scalar_one_or_none()

    profile_text = "<b>Профиль клиента:</b>\n\n"
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
        profile_text += f"Тип линз: {last_vision.lens_type or '—'}\n"
        profile_text += f"Модель оправы: {last_vision.frame_model or '—'}\n"
        if last_vision.note:
            profile_text += f"Примечание: {last_vision.note}\n"
    else:
        profile_text += "<i>Записей зрения пока нет</i>\n"

    kb = [
        [InlineKeyboardButton(text="✏ Редактировать данные", callback_data=f"admin_edit_client_{person.id}")],
        [InlineKeyboardButton(text="➕ Добавить новую запись зрения", callback_data=f"admin_add_vision_{person.id}")],
        [InlineKeyboardButton(text="📜 Просмотреть все записи зрения", callback_data=f"admin_view_all_visions_{person.id}")],
        [InlineKeyboardButton(text="◀ Назад к поиску", callback_data="admin_back_to_search")],
        [InlineKeyboardButton(text="◀ В админ-меню", callback_data="admin_back_to_menu")],
    ]

    if isinstance(trigger, Message):
        await trigger.answer(profile_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        try:
            await trigger.message.delete()
        except TelegramBadRequest:
            pass

        await bot.send_message(
            trigger.from_user.id,
            profile_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
        )

    await state.update_data(person_id=person.id)
    await state.set_state(AdminClientsStates.viewing_profile)

# Выбор профиля из списка
@admin_clients_router.callback_query(F.data.startswith("admin_client_profile_"))
async def select_admin_profile(callback: CallbackQuery, state: FSMContext, bot: Bot):
    person_id = int(callback.data.split("_")[3])
    async with AsyncSessionLocal() as session:
        person = await session.get(Person, person_id)
    if person:
        await admin_show_profile(callback, person, state, bot)
    await callback.answer()

# Назад к поиску
@admin_clients_router.callback_query(F.data == "admin_back_to_search")
async def admin_back_to_search(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await bot.send_message(
        callback.from_user.id,
        "🔍 <b>Поиск клиента</b>\n\n"
        "Введите номер телефона, telegram_id или часть имени/фамилии.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Отмена", callback_data="admin_clients_cancel")]
        ])
    )
    await state.set_state(AdminClientsStates.waiting_search_query)
    await callback.answer()

# Возврат в админ-меню
@admin_clients_router.callback_query(F.data == "admin_back_to_menu")
async def admin_back_to_menu(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await bot.send_message(
        callback.from_user.id,
        "🛠 <b>Панель администратора</b>\n\nВыберите раздел:",
        reply_markup=get_admin_main_keyboard()
    )
    await state.set_state(AdminMainStates.admin_menu)
    await callback.answer()

# Начать редактирование
@admin_clients_router.callback_query(AdminClientsStates.viewing_profile, F.data.startswith("admin_edit_client_"))
async def admin_start_edit_client(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await has_admin_access(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    person_id = int(callback.data.split("_")[3])
    await state.update_data(person_id=person_id)

    await bot.send_message(
        callback.from_user.id,
        "✏ <b>Редактирование данных клиента</b>\n\n"
        "Введите данные через пробел в формате:\n"
        "Имя Фамилия Возраст\n\n"
        "Примеры:\n"
        "Иван Иванов 25\n"
        "Иван Иванов\n"
        "Иван 25\n"
        "25\n\n"
        "Пропущенные поля останутся без изменений.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Отмена", callback_data="admin_cancel_edit_client")]
        ])
    )
    await state.set_state(AdminClientsStates.editing_client_data)
    await callback.answer()

# Отмена редактирования
@admin_clients_router.callback_query(AdminClientsStates.editing_client_data, F.data == "admin_cancel_edit_client")
async def admin_cancel_edit_client(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await has_admin_access(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    data = await state.get_data()
    person_id = data.get("person_id")

    if person_id:
        async with AsyncSessionLocal() as session:
            person = await session.get(Person, person_id)
        if person:
            await admin_show_profile(callback, person, state, bot)

    await state.set_state(AdminClientsStates.viewing_profile)
    await callback.answer("Редактирование отменено")

# Обработка редактирования данных клиента
@admin_clients_router.message(AdminClientsStates.editing_client_data)
async def admin_process_edit_client(message: Message, state: FSMContext, bot: Bot):
    if not await has_admin_access(message.from_user.id):
        return

    data = await state.get_data()
    person_id = data.get("person_id")

    async with AsyncSessionLocal() as session:
        person = await session.get(Person, person_id)
        if not person:
            await message.answer("❌ Клиент не найден.")
            await state.set_state(AdminClientsStates.waiting_search_query)
            return

        # Сохраняем все нужные данные ДО commit
        full_name = person.full_name
        age = person.age
        phone = person.phone
        telegram_id = person.telegram_id
        role = person.role
        reg_date = person.created_at.date() if person.created_at else '—'
        last_visit = person.last_visit_date or '—'

        words = message.text.strip().split()

        changes = []

        if len(words) >= 1:
            person.first_name = words[0]
            changes.append("Имя")

        if len(words) >= 2:
            person.last_name = words[1]
            changes.append("Фамилия")

        if len(words) >= 3 and words[2].isdigit():
            person.age = int(words[2])
            changes.append("Возраст")

        if changes:
            await session.commit()
            await message.answer(f"✅ Данные обновлены: {', '.join(changes)}")
        else:
            await message.answer("Ничего не изменено. Укажите хотя бы одно значение.")

        # Формируем профиль из сохранённых переменных (без доступа к person после commit)
        profile_text = "<b>Обновлённый профиль клиента:</b>\n\n"
        profile_text += f"ФИО: {full_name or '—'}\n"
        profile_text += f"Возраст: {age or '—'}\n"
        profile_text += f"Телефон: {phone or '—'}\n"
        profile_text += f"Telegram ID: {telegram_id or '—'}\n"
        profile_text += f"Роль: {role}\n"
        profile_text += f"Дата регистрации: {reg_date}\n"
        profile_text += f"Последний визит: {last_visit}"

        kb = [
            [InlineKeyboardButton(text="✏ Редактировать данные", callback_data=f"admin_edit_client_{person_id}")],
            [InlineKeyboardButton(text="➕ Добавить новую запись зрения", callback_data=f"admin_add_vision_{person_id}")],
            [InlineKeyboardButton(text="📜 Просмотреть все записи зрения", callback_data=f"admin_view_all_visions_{person_id}")],
            [InlineKeyboardButton(text="◀ Назад к поиску", callback_data="admin_back_to_search")],
            [InlineKeyboardButton(text="◀ В админ-меню", callback_data="admin_back_to_menu")],
        ]

        await message.answer(profile_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        await state.set_state(AdminClientsStates.viewing_profile)