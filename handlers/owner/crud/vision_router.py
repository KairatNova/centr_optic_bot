from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from sqlalchemy import select

from database.models import Person, Vision
from database.session import AsyncSessionLocal
from config import OWNER_IDS
from forms.forms_fsm import OwnerClientsStates  
from datetime import date

from handlers.owner.crud.clients_router import show_client_profile 


owner_vision_router = Router()

def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS



# Начало добавления записи зрения
@owner_vision_router.callback_query(OwnerClientsStates.viewing_client_profile, F.data.startswith("add_vision_"))
async def start_add_vision(callback: CallbackQuery, state: FSMContext, bot: Bot):
    person_id = int(callback.data.split("_")[2])
    await state.update_data(person_id=person_id)

    await bot.send_message(
        callback.from_user.id,
        "➕ <b>Добавление новой записи зрения</b>\n\n"
        "<b>Шаг 1/3:</b> Введите параметры для правого и левого глаза в одном сообщении.\n\n"
        "Формат (6 значений через пробел):\n"
        "Правая SPH  Правая CYL  Правая AXIS\n"
        "Левая SPH   Левая CYL   Левая AXIS\n\n"
        "Пример:\n"
        "-1.50 -0.50 180\n"
        "-2.00 -1.00 90\n\n"
        "Значения могут быть с минусом или плюсом. Если какое-то поле пустое — используйте 0 или -.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Отмена", callback_data="cancel_add_vision")]
        ])
    )
    await state.set_state(OwnerClientsStates.waiting_sph_cyl_axis)
    await callback.answer()

# Отмена добавления на любом этапе
@owner_vision_router.callback_query(F.data == "cancel_add_vision")
async def cancel_add_vision(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    person_id = data.get("person_id")

    if person_id:
        async with AsyncSessionLocal() as session:
            person = await session.get(Person, person_id)
        if person:
            from handlers.owner.crud.clients_router  import show_client_profile 
            await show_client_profile(callback, person, state, bot)

    await callback.answer("Добавление записи отменено")

# Шаг 1: Ввод SPH, CYL, AXIS для правого и левого
@owner_vision_router.message(OwnerClientsStates.waiting_sph_cyl_axis)
async def process_sph_cyl_axis(message: Message, state: FSMContext, bot: Bot):
    if not is_owner(message.from_user.id):
        return

    values = message.text.strip().split()
    if len(values) != 6:
        await message.answer(
            "❌ Неверный формат. Нужно ровно 6 значений (SPH, CYL, AXIS для правого и левого).\n"
            "Повторите ввод или отмените.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀ Отмена", callback_data="cancel_add_vision")]
            ])
        )
        return

    try:
        sph_r, cyl_r, axis_r, sph_l, cyl_l, axis_l = map(float, values[:3] + values[3:])
        # AXIS обычно int, но float ок
        axis_r = int(axis_r)
        axis_l = int(axis_l)
    except ValueError:
        await message.answer("❌ Все значения должны быть числами (например -1.5 или 180). Повторите.")
        return

    await state.update_data(
        sph_r=sph_r, cyl_r=cyl_r, axis_r=axis_r,
        sph_l=sph_l, cyl_l=cyl_l, axis_l=axis_l
    )

    await message.answer(
        "<b>Шаг 2/3:</b> Введите PD, тип линз и модель оправы в одном сообщении.\n\n"
        "Формат:\n"
        "PD lens_type frame_model\n\n"
        "Пример:\n"
        "62 progressive Ray-Ban RB2132\n\n"
        "PD — число (например 62).\n\n"
        "lens_type и frame_model — текст (можно пропустить, написав только PD).",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Отмена", callback_data="cancel_add_vision")]
        ])
    )
    await state.set_state(OwnerClientsStates.waiting_pd_lens_frame)

# Шаг 2: PD, lens_type, frame_model
@owner_vision_router.message(OwnerClientsStates.waiting_pd_lens_frame)
async def process_pd_lens_frame(message: Message, state: FSMContext, bot: Bot):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.strip().split(maxsplit=2)

    if len(parts) < 1:
        await message.answer("❌ Укажите хотя бы PD. Повторите.")
        return

    try:
        pd = float(parts[0])
    except ValueError:
        await message.answer("❌ PD должен быть числом. Повторите.")
        return

    lens_type = parts[1] if len(parts) >= 2 else None
    frame_model = parts[2] if len(parts) >= 3 else None

    await state.update_data(pd=pd, lens_type=lens_type, frame_model=frame_model)

    await message.answer(
        "<b>Шаг 3/3:</b> Введите примечание (опционально).\n\n"
        "Можно написать любой текст или просто отправить пустое сообщение/нажать Отмена.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Отмена", callback_data="cancel_add_vision")]
        ])
    )
    await state.set_state(OwnerClientsStates.waiting_note)

# Шаг 3: Note и сохранение
@owner_vision_router.message(OwnerClientsStates.waiting_note)
async def process_note_and_save(message: Message, state: FSMContext, bot: Bot):
    if not is_owner(message.from_user.id):
        return

    note = message.text.strip() if message.text else None

    data = await state.get_data()
    person_id = data["person_id"]

    async with AsyncSessionLocal() as session:
        person = await session.get(Person, person_id)
        if not person:
            await message.answer("❌ Клиент не найден.")
            await state.clear()
            return

        new_vision = Vision(
            person_id=person_id,
            visit_date=date.today(),
            sph_r=data.get("sph_r"),
            cyl_r=data.get("cyl_r"),
            axis_r=data.get("axis_r"),
            sph_l=data.get("sph_l"),
            cyl_l=data.get("cyl_l"),
            axis_l=data.get("axis_l"),
            pd=data.get("pd"),
            lens_type=data.get("lens_type"),
            frame_model=data.get("frame_model"),
            note=note
        )
        session.add(new_vision)

   
        person.last_visit_date = date.today()

        await session.commit()

    await message.answer("✅ Новая запись зрения успешно добавлена!")


    await show_client_profile(message, person, state, bot)
    await state.set_state(OwnerClientsStates.viewing_client_profile)