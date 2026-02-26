from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from sqlalchemy import select
from database.models import Person
from database.session import AsyncSessionLocal
from datetime import date

from forms.forms_fsm import RegistrationStates
from keyboards.client_kb import get_client_keyboard


start_router = Router()

# Клавиатура для запроса телефона
phone_request_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Поделиться номером телефона", request_contact=True)]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)



@start_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        # Проверяем, есть ли уже пользователь в БД
        result = await session.execute(
            select(Person).where(Person.telegram_id == message.from_user.id)
        )
        person: Person | None = result.scalar_one_or_none()

        if person is None:
            # Создаём нового пользователя
            person = Person(
                telegram_id=message.from_user.id,
                username=message.from_user.username,          # Может быть None
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                role="client"
            )
            session.add(person)
            await session.commit()
            await session.refresh(person)  # Чтобы получить id

            welcome_text = "Спасибо за регистрацию! 👋\nДля удобной записи на приём и для получении акции от магазина, "
        else:
            # Обновляем данные (username и имена могут измениться)
            person.username = message.from_user.username or person.username

            await session.commit()

            welcome_text = f"С возвращением, {message.from_user.first_name or 'друг'}! 👋"

        # Проверяем, есть ли телефон
        if person.phone is None:
            await message.answer(
                f"{welcome_text}\n\n"
                "Пожалуйста, поделитесь номером телефона, нажав кнопку ниже 👇",
                reply_markup=phone_request_kb
            )
            await state.set_state(RegistrationStates.waiting_for_phone)
        else:
            # Телефон уже есть — сразу показываем основное меню
            await message.answer(
                f"{welcome_text}\nВыберите нужный пункт в меню:",
                reply_markup=get_client_keyboard()
            )
            await state.clear()  # На всякий случай

# Обработка полученного контакта
@start_router.message(RegistrationStates.waiting_for_phone, F.contact)
async def process_phone(message: Message, state: FSMContext):
    phone_number = message.contact.phone_number
    
    # Нормализуем номер (убираем + если есть, чтобы избежать дубликатов)
    if phone_number.startswith("+"):
        phone_number = phone_number[1:]

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Person).where(Person.telegram_id == message.from_user.id)
        )
        person: Person = result.scalar_one()

        # Проверяем, не занят ли номер другим пользователем
        existing = await session.execute(
            select(Person).where(Person.phone == phone_number, Person.id != person.id)
        )
        if existing.scalar_one_or_none():
            await message.answer(
                "Этот номер телефона уже зарегистрирован за другим аккаунтом.\n"
                "Если это ошибка — обратитесь к администратору.",
                reply_markup=ReplyKeyboardRemove()
            )
            return

        person.phone = phone_number
        await session.commit()

    await message.answer(
        "Спасибо! Номер телефона успешно сохранён 📱\n"
        "Теперь вы можете пользоваться всеми функциями бота.\n"
        "Выберите нужный пункт в меню:",
        reply_markup=get_client_keyboard()
    )
    await state.clear()

# Если пользователь отправил что-то другое в состоянии ожидания телефона
@start_router.message(RegistrationStates.waiting_for_phone)
async def invalid_phone(message: Message):
    await message.answer(
        "Пожалуйста, отправьте номер телефона, нажав кнопку «Поделиться номером телефона» 👇",
        reply_markup=phone_request_kb
    )

