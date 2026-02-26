from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from sqlalchemy import select, delete

from database.models import Person, Vision
from database.session import AsyncSessionLocal
from config import OWNER_IDS
from forms.forms_fsm import AdminClientsStates
from datetime import date

# Импорт функции показа профиля админа
from .admin_clients_router import admin_show_profile  # замените на ваш путь

admin_vision_edit_router = Router()

async def has_admin_access(user_id: int) -> bool:
    if user_id in OWNER_IDS:
        return True

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Person.role).where(Person.telegram_id == user_id)
        )
        role = result.scalar_one_or_none()
        return role in ("admin", "owner")

# Просмотр всех записей — показываем первую (последнюю по дате)
@admin_vision_edit_router.callback_query(F.data.startswith("admin_view_all_visions_"))
async def admin_view_all_visions(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await has_admin_access(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    person_id = int(callback.data.split("_")[4])

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Vision)
            .where(Vision.person_id == person_id)
            .order_by(Vision.visit_date.desc())
        )
        visions = result.scalars().all()

    if not visions:
        await callback.answer("У клиента нет записей зрения.", show_alert=True)
        return

    # Сохраняем список ID и текущий индекс
    await state.update_data(visions_ids=[v.id for v in visions], current_vision_index=0, person_id=person_id)
    await admin_show_vision_record(callback, 0, visions, bot, state)
    await callback.answer()

# Показ одной записи с пагинацией
async def admin_show_vision_record(trigger, index: int, visions: list[Vision], bot: Bot, state: FSMContext):
    v = visions[index]

    text = f"<b>Запись зрения от {v.visit_date}</b>\n\n"
    text += f"Правая: SPH {v.sph_r or '—'} | CYL {v.cyl_r or '—'} | AXIS {v.axis_r or '—'}\n"
    text += f"Левая: SPH {v.sph_l or '—'} | CYL {v.cyl_l or '—'} | AXIS {v.axis_l or '—'}\n"
    text += f"PD: {v.pd or '—'}\n"
    text += f"Тип линз: {v.lens_type or '—'}\n"
    text += f"Модель оправы: {v.frame_model or '—'}\n"
    if v.note:
        text += f"Примечание: {v.note}\n"
    text += f"\nЗапись {index + 1} из {len(visions)}"

    kb = [
        [
            InlineKeyboardButton(text="◀", callback_data=f"admin_vision_prev_{index}"),
            InlineKeyboardButton(text="▶", callback_data=f"admin_vision_next_{index}"),
        ],
        [InlineKeyboardButton(text="✏ Редактировать эту запись", callback_data=f"admin_edit_this_vision_{v.id}")],
        [InlineKeyboardButton(text="🗑 Удалить эту запись", callback_data=f"admin_delete_this_vision_{v.id}")],
        [InlineKeyboardButton(text="◀ Назад в профиль", callback_data=f"admin_back_to_profile_{v.person_id}")],
    ]

    if isinstance(trigger, Message):
        await trigger.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await trigger.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# Навигация предыдущая/следующая
@admin_vision_edit_router.callback_query(F.data.startswith("admin_vision_prev_") | F.data.startswith("admin_vision_next_"))
async def admin_navigate_vision(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await has_admin_access(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    data = await state.get_data()
    visions_ids = data.get("visions_ids", [])
    current_index = int(callback.data.split("_")[3])

    if "prev" in callback.data:
        new_index = max(0, current_index - 1)
    else:
        new_index = min(len(visions_ids) - 1, current_index + 1)

    async with AsyncSessionLocal() as session:
        visions = [await session.get(Vision, vid) for vid in visions_ids]

    await admin_show_vision_record(callback, new_index, visions, bot, state)
    await state.update_data(current_vision_index=new_index)
    await callback.answer()

# Удаление записи
@admin_vision_edit_router.callback_query(F.data.startswith("admin_delete_this_vision_"))
async def admin_confirm_delete_vision(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await has_admin_access(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    vision_id = int(callback.data.split("_")[4])

    kb = [
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"admin_confirm_delete_vision_{vision_id}")],
        [InlineKeyboardButton(text="❌ Нет, отменить", callback_data="admin_cancel_delete_vision")],
    ]

    await bot.send_message(
        callback.from_user.id,
        "🗑 Вы уверены, что хотите удалить эту запись зрения?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )
    await callback.answer()

# Подтверждение удаления
@admin_vision_edit_router.callback_query(F.data.startswith("admin_confirm_delete_vision_"))
async def admin_process_delete_vision(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await has_admin_access(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    vision_id = int(callback.data.split("_")[4])
    data = await state.get_data()
    person_id = data.get("person_id")

    async with AsyncSessionLocal() as session:
        await session.execute(delete(Vision).where(Vision.id == vision_id))
        await session.commit()

    await callback.answer("✅ Запись удалена!", show_alert=True)

    # Возврат в профиль
    async with AsyncSessionLocal() as session:
        person = await session.get(Person, person_id)
        if person:
            await admin_show_profile(callback, person, state, bot)

# Отмена удаления
@admin_vision_edit_router.callback_query(F.data == "admin_cancel_delete_vision")
async def admin_cancel_delete_vision(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer("Удаление отменено", show_alert=True)

# Кнопка "Назад в профиль" — перехват
@admin_vision_edit_router.callback_query(F.data.startswith("admin_back_to_profile_"))
async def admin_back_to_profile(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await has_admin_access(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    person_id = int(callback.data.split("_")[4])

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    async with AsyncSessionLocal() as session:
        person = await session.get(Person, person_id)
        if not person:
            await callback.answer("Клиент не найден.", show_alert=True)
            return

    await admin_show_profile(callback, person, state, bot)
    await callback.answer("Возврат в профиль")

# Редактирование записи — начало
@admin_vision_edit_router.callback_query(F.data.startswith("admin_edit_this_vision_"))
async def admin_start_edit_vision(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await has_admin_access(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    vision_id = int(callback.data.split("_")[4])

    async with AsyncSessionLocal() as session:
        vision = await session.get(Vision, vision_id)
        if not vision:
            await callback.answer("Запись не найдена.", show_alert=True)
            return

    await state.update_data(vision_id=vision_id, person_id=vision.person_id)

    current_values = f"Текущие значения:\n"
    current_values += f"Правая: SPH {vision.sph_r or '—'} | CYL {vision.cyl_r or '—'} | AXIS {vision.axis_r or '—'}\n"
    current_values += f"Левая: SPH {vision.sph_l or '—'} | CYL {vision.cyl_l or '—'} | AXIS {vision.axis_l or '—'}\n"

    await bot.send_message(
        callback.from_user.id,
        "✏ <b>Редактирование записи зрения</b>\n\n"
        f"{current_values}\n\n"
        "<b>Шаг 1/3:</b> Введите новые параметры для правого и левого глаза (6 значений через пробел), или отправьте пустое сообщение для пропуска.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Отмена", callback_data="admin_cancel_edit_to_list")]
        ])
    )
    await state.set_state(AdminClientsStates.waiting_sph_cyl_axis_edit)
    await callback.answer()

# Шаг 1 редактирования: SPH, CYL, AXIS
@admin_vision_edit_router.message(AdminClientsStates.waiting_sph_cyl_axis_edit)
async def admin_process_sph_cyl_axis_edit(message: Message, state: FSMContext, bot: Bot):
    if not await has_admin_access(message.from_user.id):
        return

    text = message.text.strip()
    data = await state.get_data()
    vision_id = data["vision_id"]

    async with AsyncSessionLocal() as session:
        vision = await session.get(Vision, vision_id)

        if text:
            values = text.split()
            if len(values) != 6:
                await message.answer(
                    "❌ Неверный формат. Нужно ровно 6 значений или пустое сообщение для пропуска."
                )
                return

            try:
                vision.sph_r, vision.cyl_r, vision.axis_r = map(float, values[:3])
                vision.sph_l, vision.cyl_l, vision.axis_l = map(float, values[3:])
                vision.axis_r = int(vision.axis_r)
                vision.axis_l = int(vision.axis_l)
                await session.commit()
            except ValueError:
                await message.answer("❌ Все значения должны быть числами. Повторите.")
                return

    current_values = f"Текущие: PD {vision.pd or '—'} | Lens: {vision.lens_type or '—'} | Frame: {vision.frame_model or '—'}\n"

    await message.answer(
        "<b>Шаг 2/3:</b> Введите PD, тип линз, модель оправы (через пробел), или пустое сообщение для пропуска.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Отмена", callback_data="admin_cancel_edit_to_list")]
        ])
    )
    await state.set_state(AdminClientsStates.waiting_pd_lens_frame_edit)

# Шаг 2 редактирования: PD, lens_type, frame_model
@admin_vision_edit_router.message(AdminClientsStates.waiting_pd_lens_frame_edit)
async def admin_process_pd_lens_frame_edit(message: Message, state: FSMContext, bot: Bot):
    if not await has_admin_access(message.from_user.id):
        return

    text = message.text.strip()
    data = await state.get_data()
    vision_id = data["vision_id"]

    async with AsyncSessionLocal() as session:
        vision = await session.get(Vision, vision_id)

        if text:
            parts = text.split(maxsplit=2)
            if len(parts) < 1:
                await message.answer("❌ Укажите хотя бы PD или пустое сообщение для пропуска.")
                return

            try:
                vision.pd = float(parts[0])
            except ValueError:
                await message.answer("❌ PD должен быть числом. Повторите.")
                return

            if len(parts) >= 2:
                vision.lens_type = parts[1] or None

            if len(parts) >= 3:
                vision.frame_model = parts[2] or None

            await session.commit()

    current_note = f"Текущий: {vision.note or '—'}\n"

    await message.answer(
        "<b>Шаг 3/3:</b> Введите новое примечание, или пустое сообщение для пропуска.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Отмена", callback_data="admin_cancel_edit_to_list")]
        ])
    )
    await state.set_state(AdminClientsStates.waiting_note_edit)

# Шаг 3 редактирования: Note и завершение
@admin_vision_edit_router.message(AdminClientsStates.waiting_note_edit)
async def admin_process_note_edit(message: Message, state: FSMContext, bot: Bot):
    if not await has_admin_access(message.from_user.id):
        return

    text = message.text.strip()
    data = await state.get_data()
    vision_id = data["vision_id"]
    person_id = data["person_id"]

    async with AsyncSessionLocal() as session:
        vision = await session.get(Vision, vision_id)
        if text:
            vision.note = text
            await session.commit()

        person = await session.get(Person, person_id)
        await session.refresh(person)

    await message.answer("✅ Запись обновлена!")

    await admin_show_profile(message, person, state, bot)
    await state.set_state(AdminClientsStates.viewing_profile)

# Кнопка "Отмена" на этапах редактирования → возврат к списку всех записей
@admin_vision_edit_router.callback_query(F.data == "admin_cancel_edit_to_list")
async def admin_cancel_edit_to_list(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await has_admin_access(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    data = await state.get_data()
    visions_ids = data.get("visions_ids", [])
    person_id = data.get("person_id")

    if not visions_ids or not person_id:
        await callback.answer("Данные не найдены.", show_alert=True)
        await state.clear()
        return

    async with AsyncSessionLocal() as session:
        visions = [await session.get(Vision, vid) for vid in visions_ids]

    await admin_show_vision_record(callback, 0, visions, bot, state)
    await state.update_data(current_vision_index=0)
    await callback.answer("Редактирование отменено. Возврат к списку записей.")