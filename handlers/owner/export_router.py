from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from sqlalchemy import select, or_, func, and_
from sqlalchemy.orm import joinedload

from database.models import Person, Vision
from database.session import AsyncSessionLocal
from config import OWNER_IDS
from forms.forms_fsm import OwnerExportStates, OwnerMainStates
from keyboards.owner_kb import get_owner_main_keyboard, get_export_submenu_keyboard
import pandas as pd
from io import BytesIO

owner_export_router = Router()

def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS



@owner_export_router.callback_query(OwnerExportStates.export_menu, F.data.startswith("export_"))
async def export_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_owner(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    action = callback.data

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    if action == "export_all_clients":
        await bot.send_message(callback.from_user.id, "📊 Генерирую Excel с клиентами...")

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Person))
            persons = result.scalars().all()

        data = {
            'ID': [p.id for p in persons],
            'ФИО': [p.full_name or '—' for p in persons],
            'Имя': [p.first_name or '—' for p in persons],
            'Фамилия': [p.last_name or '—' for p in persons],
            'Возраст': [p.age or '—' for p in persons],
            'Телефон': [p.phone or '—' for p in persons],
            'Telegram ID': [p.telegram_id or '—' for p in persons],
            'Роль': [p.role for p in persons],
            'Дата регистрации': [p.created_at.date() if p.created_at else '—' for p in persons],
            'Последний визит': [p.last_visit_date or '—' for p in persons],
        }

        df = pd.DataFrame(data)
        excel_buffer = BytesIO()
        df.to_excel(excel_buffer, index=False, engine='openpyxl')
        excel_buffer.seek(0)

        await bot.send_document(
            callback.from_user.id,
            BufferedInputFile(excel_buffer.getvalue(), filename="clients.xlsx"),
            caption="✅ Выгрузка всех клиентов в Excel готова!"
        )

    elif action == "export_all_visions":
        await bot.send_message(callback.from_user.id, "📊 Генерирую Excel с записями зрения...")

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Vision).options(joinedload(Vision.person))
            )
            visions = result.scalars().unique().all()

        data = {
            'Client ID': [v.person_id for v in visions],
            'ФИО клиента': [v.person.full_name or '—' for v in visions],
            'Дата визита': [v.visit_date for v in visions],
            'SPH R': [v.sph_r or '—' for v in visions],
            'CYL R': [v.cyl_r or '—' for v in visions],
            'AXIS R': [v.axis_r or '—' for v in visions],
            'SPH L': [v.sph_l or '—' for v in visions],
            'CYL L': [v.cyl_l or '—' for v in visions],
            'AXIS L': [v.axis_l or '—' for v in visions],
            'PD': [v.pd or '—' for v in visions],
            'Тип линз': [v.lens_type or '—' for v in visions],
            'Модель оправы': [v.frame_model or '—' for v in visions],
            'Примечание': [v.note or '—' for v in visions],
        }

        df = pd.DataFrame(data)
        excel_buffer = BytesIO()
        df.to_excel(excel_buffer, index=False, engine='openpyxl')
        excel_buffer.seek(0)

        await bot.send_document(
            callback.from_user.id,
            BufferedInputFile(excel_buffer.getvalue(), filename="visions.xlsx"),
            caption="✅ Выгрузка всех записей зрения в Excel готова!"
        )

    elif action == "export_clients_last_vision":
        await bot.send_message(callback.from_user.id, "📄 Генерирую Excel с клиентами и последними записями зрения...")
    
        async with AsyncSessionLocal() as session:
            # Получаем всех клиентов
            persons_result = await session.execute(select(Person))
            persons = persons_result.scalars().all()
    
            # Для каждого клиента находим последнюю запись (коррелированный подзапрос)
            data = []
            for person in persons:
                last_vision_result = await session.execute(
                    select(Vision)
                    .where(Vision.person_id == person.id)
                    .order_by(Vision.visit_date.desc())
                    .limit(1)
                )
                last_vision = last_vision_result.scalar_one_or_none()
    
                row = {
                    'Client ID': person.id,
                    'ФИО': person.full_name or '—',
                    'Имя': person.first_name or '—',
                    'Фамилия': person.last_name or '—',
                    'Возраст': person.age or '—',
                    'Телефон': person.phone or '—',
                    'Telegram ID': person.telegram_id or '—',
                    'Роль': person.role,
                    'Дата регистрации': person.created_at.date() if person.created_at else '—',
                    'Последний визит': person.last_visit_date or '—',
                }
    
                if last_vision:
                    row.update({
                        'Дата последней записи зрения': last_vision.visit_date,
                        'SPH R': last_vision.sph_r or '—',
                        'CYL R': last_vision.cyl_r or '—',
                        'AXIS R': last_vision.axis_r or '—',
                        'SPH L': last_vision.sph_l or '—',
                        'CYL L': last_vision.cyl_l or '—',
                        'AXIS L': last_vision.axis_l or '—',
                        'PD': last_vision.pd or '—',
                        'Тип линз': last_vision.lens_type or '—',
                        'Модель оправы': last_vision.frame_model or '—',
                        'Примечание': last_vision.note or '—',
                    })
                else:
                    row.update({
                        'Дата последней записи зрения': '—',
                        'SPH R': '—', 'CYL R': '—', 'AXIS R': '—',
                        'SPH L': '—', 'CYL L': '—', 'AXIS L': '—',
                        'PD': '—', 'Тип линз': '—', 'Модель оправы': '—', 'Примечание': '—',
                    })
    
                data.append(row)
    
        df = pd.DataFrame(data)
        excel_buffer = BytesIO()
        df.to_excel(excel_buffer, index=False, engine='openpyxl')
        excel_buffer.seek(0)
    
        await bot.send_document(
            callback.from_user.id,
            BufferedInputFile(excel_buffer.getvalue(), filename="clients_with_last_vision.xlsx"),
            caption="✅ Выгрузка всех клиентов с последними записями зрения готова!"
        )
    
        await bot.send_message(
            callback.from_user.id,
            "📊 <b>Выгрузки данных</b>\n\nВыберите тип выгрузки:",
            reply_markup=get_export_submenu_keyboard()
        )
    elif action == "export_back":
        await state.set_state(OwnerMainStates.main_menu)
        await bot.send_message(
            callback.from_user.id,
            "👑 <b>Панель владельца</b>\n\nВыберите раздел:",
            reply_markup=get_owner_main_keyboard()
        )

    await callback.answer()