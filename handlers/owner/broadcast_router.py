from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
import asyncio

from sqlalchemy import select, or_

from database.models import Person, Vision
from database.session import AsyncSessionLocal
from config import OWNER_IDS
from forms.forms_fsm import OwnerBroadcastStates, OwnerMainStates
from keyboards.owner_kb import get_owner_main_keyboard, get_broadcast_submenu_keyboard

from utils.broadcast_monitor import start as broadcast_start, mark_sent as broadcast_mark_sent, finish as broadcast_finish, status as broadcast_status
from utils.audit import write_audit_event

owner_broadcast_router = Router()

def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS

def normalize_phone(input_str: str) -> str | None:
    digits = ''.join(filter(str.isdigit, input_str))
    if len(digits) == 10 and digits.startswith('0'):
        return '996' + digits[1:]
    elif len(digits) == 12 and digits.startswith('996'):
        return digits
    return None

@owner_broadcast_router.callback_query(OwnerBroadcastStates.broadcast_menu, F.data.startswith("broadcast_"))
async def broadcast_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_owner(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    action = callback.data

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    if action == "broadcast_one":
        await bot.send_message(
            callback.from_user.id,
            "🔍 <b>Поиск клиента для сообщения</b>\n\n"
            "Введите номер телефона, telegram_id или часть имени/фамилии.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀ Отмена", callback_data="broadcast_cancel_search")]
            ])
        )
        await state.set_state(OwnerBroadcastStates.waiting_search_query)

    elif action == "broadcast_all":
        # Подсчёт получателей
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Person.telegram_id).where(Person.telegram_id.is_not(None))
            )
            recipients = result.scalars().all()
            count = len(recipients)

        await state.update_data(recipients_count=count)

        await bot.send_message(
            callback.from_user.id,
            f"📢 <b>Рассылка всем клиентам</b>\n\n"
            f"Получателей: <b>{count}</b> (все зарегистрированные пользователи с Telegram ID)\n\n"
            "Введите текст сообщения для рассылки:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀ Отмена", callback_data="broadcast_cancel_all")]
            ])
        )
        await state.set_state(OwnerBroadcastStates.waiting_broadcast_text)

    elif action == "broadcast_back":
        await state.set_state(OwnerMainStates.main_menu)
        await bot.send_message(
            callback.from_user.id,
            "👑 <b>Панель владельца</b>\n\nВыберите раздел:",
            reply_markup=get_owner_main_keyboard()
        )

    await callback.answer()

# Отмена поиска
@owner_broadcast_router.callback_query(OwnerBroadcastStates.waiting_search_query, F.data == "broadcast_cancel_search")
async def cancel_search(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_owner(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    await bot.send_message(
        callback.from_user.id,
        "📨 <b>Рассылки</b>\n\nВыберите действие:",
        reply_markup=get_broadcast_submenu_keyboard()
    )
    await state.set_state(OwnerBroadcastStates.broadcast_menu)
    await callback.answer("Поиск отменён")

# Отмена ввода текста рассылки всем
@owner_broadcast_router.callback_query(OwnerBroadcastStates.waiting_broadcast_text, F.data == "broadcast_cancel_all")
async def cancel_broadcast_text(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_owner(callback.from_user.id):
        return

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    await bot.send_message(
        callback.from_user.id,
        "📨 <b>Рассылки</b>\n\nВыберите действие:",
        reply_markup=get_broadcast_submenu_keyboard()
    )
    await state.set_state(OwnerBroadcastStates.broadcast_menu)
    await callback.answer("Рассылка отменена")

# Ввод текста рассылки всем
@owner_broadcast_router.message(OwnerBroadcastStates.waiting_broadcast_text)
async def process_broadcast_text(message: Message, state: FSMContext, bot: Bot):
    if not is_owner(message.from_user.id):
        return

    text = message.text.strip()
    data = await state.get_data()
    count = data.get("recipients_count", 0)

    if not text:
        await message.answer("Текст не может быть пустым. Введите заново или отмените.")
        return

    await state.update_data(broadcast_text=text)

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, отправить", callback_data="broadcast_confirm_yes")],
        [InlineKeyboardButton(text="❌ Нет, отменить", callback_data="broadcast_confirm_no")],
    ])

    await message.answer(
        f"Подтвердите рассылку:\n\n"
        f"<b>Текст:</b>\n{text}\n\n"
        f"<b>Получателей:</b> {count}\n\n"
        f"Рассылка займёт примерно {count} секунд.",
        reply_markup=confirm_kb
    )

# Подтверждение рассылки всем
@owner_broadcast_router.callback_query(F.data.startswith("broadcast_confirm_"))
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_owner(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    action = callback.data

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    data = await state.get_data()
    text = data.get("broadcast_text")
    count = data.get("recipients_count", 0)

    if action == "broadcast_confirm_no":
        await bot.send_message(
            callback.from_user.id,
            "Рассылка отменена.",
            reply_markup=get_broadcast_submenu_keyboard()
        )
        await state.set_state(OwnerBroadcastStates.broadcast_menu)
        await callback.answer()
        return

    # Запуск рассылки
    broadcast_start(total=count, requested_by=callback.from_user.id)
    write_audit_event(callback.from_user.id, "owner", "broadcast_all_start", {"total": count})
    progress_message = await bot.send_message(
        callback.from_user.id,
        f"📢 Рассылка начата...\nОтправлено: 0 из {count}"
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Person).where(Person.telegram_id.is_not(None))
        )
        recipients = result.scalars().all()

    sent = 0
    errors = 0

    for person in recipients:
        try:
            await bot.send_message(person.telegram_id, text)
            sent += 1
            broadcast_mark_sent(ok=True)
        except Exception:
            errors += 1
            broadcast_mark_sent(ok=False)

        await asyncio.sleep(1.05)  # Безопасная пауза

        if broadcast_status.cancel_requested:
            break


        if sent % 20 == 0 or sent == count:
            try:
                await bot.edit_message_text(
                    chat_id=callback.from_user.id,
                    message_id=progress_message.message_id,
                    text=f"📢 Рассылка в процессе...\nОтправлено: {sent} из {count}\nОшибок: {errors}"
                )
            except TelegramBadRequest:
                pass
    broadcast_finish()
    write_audit_event(callback.from_user.id, "owner", "broadcast_all_finish", {"sent": sent, "errors": errors})

    cancelled_note = "\n⛔ Остановлена вручную" if broadcast_status.cancel_requested else ""

    await bot.send_message(
        callback.from_user.id,
        f"✅ Рассылка завершена!\nУспешно: {sent}\nОшибок: {errors}{cancelled_note}",
        reply_markup=get_broadcast_submenu_keyboard()
    )
    await state.set_state(OwnerBroadcastStates.broadcast_menu)
    await callback.answer()

# Отмена поиска — возврат в подменю рассылок
@owner_broadcast_router.callback_query(OwnerBroadcastStates.waiting_search_query, F.data == "broadcast_cancel_search")
async def cancel_search(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_owner(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    await bot.send_message(
        callback.from_user.id,
        "📨 <b>Рассылки</b>\n\nВыберите действие:",
        reply_markup=get_broadcast_submenu_keyboard()
    )
    await state.set_state(OwnerBroadcastStates.broadcast_menu)
    await callback.answer("Поиск отменён")

# Поиск клиентов
@owner_broadcast_router.message(OwnerBroadcastStates.waiting_search_query)
async def process_search(message: Message, state: FSMContext, bot: Bot):
    if not is_owner(message.from_user.id):
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
            select(Person).where(or_(*conditions)).limit(20)
        )
        persons = result.scalars().all()

    if not persons:
        await message.answer(
            "❌ Клиенты не найдены. Попробуйте другой запрос.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀ Отмена", callback_data="broadcast_cancel_search")]
            ])
        )
        return

    if len(persons) == 1:
        await show_profile(message, persons[0], state, bot)
        return


    kb = []
    for p in persons:
        name = p.full_name or p.phone or str(p.telegram_id)
        kb.append([InlineKeyboardButton(text=name, callback_data=f"profile_{p.id}")])

    kb.append([InlineKeyboardButton(text="◀ Отмена", callback_data="broadcast_cancel_search")])

    await message.answer(
        f"🔍 Найдено {len(persons)} клиентов. Выберите:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )


async def show_profile(trigger, person: Person, state: FSMContext, bot: Bot):
    async with AsyncSessionLocal() as session:
        visions_result = await session.execute(
            select(Vision).where(Vision.person_id == person.id).order_by(Vision.visit_date.desc()).limit(5)
        )
        visions = visions_result.scalars().all()

    profile_text = f"👤 <b>Профиль клиента</b>\n\n"
    profile_text += f"ФИО: {person.full_name or 'Не указано'}\n"
    profile_text += f"Телефон: {person.phone or 'Не указан'}\n"
    profile_text += f"Telegram ID: {person.telegram_id or 'Не зарегистрирован'}\n"
    profile_text += f"Роль: {person.role}\n"
    profile_text += f"Дата регистрации: {person.created_at.date() if person.created_at else '—'}\n"
    profile_text += f"Последний визит: {person.last_visit_date or '—'}\n\n"

    if visions:
        profile_text += "<b>Записи зрения (последние 5):</b>\n\n"
        for v in visions:
            profile_text += f"📅 {v.visit_date}\n"
            profile_text += f"Правая: SPH {v.sph_r or '-'} | CYL {v.cyl_r or '-'} | AXIS {v.axis_r or '-'}\n"
            profile_text += f"Левая: SPH {v.sph_l or '-'} | CYL {v.cyl_l or '-'} | AXIS {v.axis_l or '-'}\n"
            profile_text += f"PD: {v.pd or '-'}\n"
            if v.note:
                profile_text += f"Примечание: {v.note}\n"
            if v.frame_model or v.lens_type:
                profile_text += f"Оправа/Линзы: {v.frame_model or ''} {v.lens_type or ''}\n"
            profile_text += "\n"
    else:
        profile_text += "👁 <i>Записей зрения пока нет. Приходите на приём!</i>\n"

    kb = [
        [InlineKeyboardButton(text="📨 Отправить сообщение", callback_data=f"send_msg_{person.id}")],
        [InlineKeyboardButton(text="◀ Назад к поиску", callback_data="back_to_search")]
    ]

    if isinstance(trigger, Message):
        await trigger.answer(profile_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await trigger.message.edit_text(profile_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

    await state.update_data(person_id=person.id)
    await state.set_state(OwnerBroadcastStates.viewing_profile)


@owner_broadcast_router.callback_query(F.data.startswith("profile_"))
async def select_profile(callback: CallbackQuery, state: FSMContext, bot: Bot):
    person_id = int(callback.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        person = await session.get(Person, person_id)
    if person:
        await show_profile(callback, person, state, bot)
    await callback.answer()


@owner_broadcast_router.callback_query(OwnerBroadcastStates.viewing_profile, F.data.startswith("send_msg_"))
async def start_send_message(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await bot.send_message(
        callback.from_user.id,
        "📨 Введите текст сообщения для отправки клиенту:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Отмена", callback_data="back_to_profile")]
        ])
    )
    await state.set_state(OwnerBroadcastStates.waiting_message_text)
    await callback.answer()

# Отмена отправки
@owner_broadcast_router.callback_query(F.data == "back_to_profile")
async def back_to_profile(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    person_id = data.get("person_id")
    
    if person_id:
        async with AsyncSessionLocal() as session:
            person = await session.get(Person, person_id)
        if person:
            await show_profile(callback, person, state, bot)
    await callback.answer()

# Обработка текста сообщения
@owner_broadcast_router.message(OwnerBroadcastStates.waiting_message_text)
async def send_message_to_client(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    person_id = data.get("person_id")

    async with AsyncSessionLocal() as session:
        person = await session.get(Person, person_id)

    if not person or not person.telegram_id:
        await message.answer("❌ Ошибка: клиент не найден или нет Telegram ID.")
        await state.set_state(OwnerBroadcastStates.broadcast_menu)
        return

    try:
        await bot.send_message(person.telegram_id, message.text)
        await message.answer(f"✅ Сообщение отправлено клиенту {person.full_name or person.telegram_id}!")
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки: {str(e)}")

    # Возврат к профилю
    await show_profile(message, person, state, bot)

# Назад к поиску из профиля

@owner_broadcast_router.callback_query(OwnerBroadcastStates.viewing_profile, F.data == "back_to_search")
async def back_to_search(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await bot.send_message(
        callback.from_user.id,
        "🔍 <b>Поиск клиента для сообщения</b>\n\n"
        "Введите номер телефона, telegram_id или часть имени/фамилии.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Отмена", callback_data="broadcast_cancel_search")]
        ])
    )
    await state.set_state(OwnerBroadcastStates.waiting_search_query)
    await callback.answer()


@owner_broadcast_router.callback_query(F.data == "broadcast_back")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()  
    await bot.send_message(
        callback.from_user.id,
        "🔙 Возврат в главное меню владельца",
        reply_markup=get_owner_main_keyboard()
    )
    await callback.answer()
