
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from sqlalchemy import select, delete

from database.models import Person, Vision
from database.session import AsyncSessionLocal
from config import OWNER_IDS
from forms.forms_fsm import OwnerClientsStates  # добавьте новые состояния
from datetime import date

from handlers.owner.crud.clients_router import show_client_profile


owner_vision_edit_router = Router()

def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS


# Просмотр всех записей — показываем первую (последнюю по дате)
@owner_vision_edit_router.callback_query(F.data.startswith("view_all_visions_"))
async def view_all_visions(callback: CallbackQuery, state: FSMContext, bot: Bot):
    person_id = int(callback.data.split("_")[3])

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

    # Показываем первую запись (index 0 = latest)
    await state.update_data(visions_ids=[v.id for v in visions], current_vision_index=0, person_id=person_id)
    await show_vision_record(callback, 0, visions, bot, state)
    await callback.answer()

# Показ одной записи с пагинацией
async def show_vision_record(trigger, index: int, visions: list[Vision], bot: Bot, state: FSMContext):
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
        InlineKeyboardButton(text="◀", callback_data=f"vision_prev_{index}"),
        InlineKeyboardButton(text="▶", callback_data=f"vision_next_{index}"),
    ],
    [InlineKeyboardButton(text="✏ Редактировать эту запись", callback_data=f"edit_this_vision_{v.id}")],
    [InlineKeyboardButton(text="🗑 Удалить эту запись", callback_data=f"delete_this_vision_{v.id}")],
    [InlineKeyboardButton(text="📄 Выгрузить в PDF", callback_data=f"export_pdf_{v.id}")],
    [InlineKeyboardButton(text="◀ Назад в профиль", callback_data=f"back_to_profile_{visions[0].person_id}")],
]

    if isinstance(trigger, Message):
        await trigger.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await trigger.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# Навигация предыдущая/следующая
@owner_vision_edit_router.callback_query(F.data.startswith("vision_prev_") | F.data.startswith("vision_next_"))
async def navigate_vision(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    visions_ids = data.get("visions_ids", [])
    current_index = int(callback.data.split("_")[2])

    if "prev" in callback.data:
        new_index = max(0, current_index - 1)
    else:
        new_index = min(len(visions_ids) - 1, current_index + 1)

    async with AsyncSessionLocal() as session:
        visions = [await session.get(Vision, vid) for vid in visions_ids]

    await show_vision_record(callback, new_index, visions, bot, state)
    await state.update_data(current_vision_index=new_index)
    await callback.answer()

# Удаление записи
@owner_vision_edit_router.callback_query(F.data.startswith("delete_this_vision_"))
async def confirm_delete_vision(callback: CallbackQuery, state: FSMContext, bot: Bot):
    vision_id = int(callback.data.split("_")[3])

    kb = [
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_vision_{vision_id}")],
        [InlineKeyboardButton(text="❌ Нет, отменить", callback_data="cancel_delete_vision")],
    ]

    await bot.send_message(
        callback.from_user.id,
        "🗑 Вы уверены, что хотите удалить эту запись зрения?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )
    await callback.answer()

# Подтверждение удаления
@owner_vision_edit_router.callback_query(F.data.startswith("confirm_delete_vision_"))
async def process_delete_vision(callback: CallbackQuery, state: FSMContext, bot: Bot):
    vision_id = int(callback.data.split("_")[3])
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
            await show_client_profile(callback, person, state, bot)

# Отмена удаления
@owner_vision_edit_router.callback_query(F.data == "cancel_delete_vision")
async def cancel_delete_vision(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer("Удаление отменено", show_alert=True)

# Редактирование записи
@owner_vision_edit_router.callback_query(F.data.startswith("edit_this_vision_"))
async def start_edit_vision(callback: CallbackQuery, state: FSMContext, bot: Bot):
    vision_id = int(callback.data.split("_")[3])

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
        "<b>Шаг 1/3:</b> Введите новые параметры для правого и левого глаза (6 значений через пробел), или пропустите шаг для сохранения текущих.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Отмена", callback_data="cancel_edit_vision")]
        ])
    )
    await state.set_state(OwnerClientsStates.waiting_sph_cyl_axis_edit)
    await callback.answer()

# Шаг 1 редактирования: SPH, CYL, AXIS
@owner_vision_edit_router.message(OwnerClientsStates.waiting_sph_cyl_axis_edit)
async def process_sph_cyl_axis_edit(message: Message, state: FSMContext, bot: Bot):
    if not is_owner(message.from_user.id):
        return

    values = message.text.strip().split()
    data = await state.get_data()
    vision_id = data["vision_id"]

    async with AsyncSessionLocal() as session:
        vision = await session.get(Vision, vision_id)

    if len(values) == 6:
        try:
            vision.sph_r, vision.cyl_r, vision.axis_r = map(float, values[:3])
            vision.sph_l, vision.cyl_l, vision.axis_l = map(float, values[3:])
            vision.axis_r = int(vision.axis_r)
            vision.axis_l = int(vision.axis_l)
            await session.commit()
        except ValueError:
            await message.answer("❌ Неверный формат. Повторите.")
            return

    current_values = f"Текущие: PD {vision.pd or '—'} | Lens: {vision.lens_type or '—'} | Frame: {vision.frame_model or '—'}\n"

    await message.answer(
        "<b>Шаг 2/3:</b> Введите PD, тип линз, модель оправы (через пробел), или пропустите.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Отмена", callback_data="cancel_edit_vision")]
        ])
    )
    await state.set_state(OwnerClientsStates.waiting_pd_lens_frame_edit)

# Шаг 2 редактирования: PD, lens_type, frame_model
@owner_vision_edit_router.message(OwnerClientsStates.waiting_pd_lens_frame_edit)
async def process_pd_lens_frame_edit(message: Message, state: FSMContext, bot: Bot):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.strip().split(maxsplit=2)
    data = await state.get_data()
    vision_id = data["vision_id"]

    async with AsyncSessionLocal() as session:
        vision = await session.get(Vision, vision_id)

    if len(parts) >= 1:
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
        "<b>Шаг 3/3:</b> Введите новое примечание, или пропустите.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Отмена", callback_data="cancel_edit_vision")]
        ])
    )
    await state.set_state(OwnerClientsStates.waiting_note_edit)

# Шаг 3 редактирования: Note и завершение
@owner_vision_edit_router.message(OwnerClientsStates.waiting_note_edit)
async def process_note_edit(message: Message, state: FSMContext, bot: Bot):
    if not is_owner(message.from_user.id):
        return

    note = message.text.strip() if message.text else None
    data = await state.get_data()
    vision_id = data["vision_id"]
    person_id = data["person_id"]

    async with AsyncSessionLocal() as session:
        vision = await session.get(Vision, vision_id)
        if note is not None:
            vision.note = note
            await session.commit()

        person = await session.get(Person, person_id)

    await message.answer("✅ Запись обновлена!")

    await show_client_profile(message, person, state, bot)
    await state.set_state(OwnerClientsStates.viewing_client_profile)


@owner_vision_edit_router.callback_query(OwnerClientsStates.editing_client_data, F.data == "cancel_edit_client")
async def cancel_edit_client(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_owner(callback.from_user.id):
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
            await show_client_profile(callback, person, state, bot)

    await state.set_state(OwnerClientsStates.viewing_client_profile)
    await callback.answer("Редактирование отменено")

# Отмена редактирования
@owner_vision_edit_router.callback_query(F.data == "cancel_edit_vision")
async def cancel_edit_vision(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    person_id = data.get("person_id")

    if person_id:
        async with AsyncSessionLocal() as session:
            person = await session.get(Person, person_id)
        if person:
            await show_client_profile(callback, person, state, bot)

    await callback.answer("Редактирование отменено")


# Хендлер для кнопки "Назад в профиль" (добавьте в конец файла)
@owner_vision_edit_router.callback_query(F.data.startswith("back_to_profile_"))
async def back_to_profile(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_owner(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    # Извлекаем person_id из callback_data
    # back_to_profile_123 → 123
    person_id = int(callback.data.split("_")[3])

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass  # сообщение уже удалено — нормально

    async with AsyncSessionLocal() as session:
        person = await session.get(Person, person_id)
        if not person:
            await callback.answer("Клиент не найден.", show_alert=True)
            return

    # Возврат в профиль (используем существующую функцию)
    await show_client_profile(callback, person, state, bot)
    await callback.answer("Возврат в профиль")


