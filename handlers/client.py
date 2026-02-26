
from aiogram.types import Message
from aiogram.filters import Command
from aiogram import F, Router

from services.content import get_content
from config import SECTION_NAMES
from keyboards.client_kb import get_client_keyboard

client_router = Router()

@client_router.message(Command("button"))
async def show_keyboard(message: Message):

    await message.answer("Выберите раздел:", reply_markup=get_client_keyboard())



@client_router.message(F.text == SECTION_NAMES["appointment"])
async def appointment(message: Message):
    text = await get_content("appointment")
    await message.answer(text, disable_web_page_preview=True)

@client_router.message(F.text == SECTION_NAMES["shop_address"])
async def shop_address(message: Message):
    text = await get_content("shop_address")
    await message.answer(text, disable_web_page_preview=True)

@client_router.message(F.text == SECTION_NAMES["promotions"])
async def promotions(message: Message):
    text = await get_content("promotions")
    await message.answer(text)

@client_router.message(F.text == SECTION_NAMES["catalog"])
async def catalog(message: Message):
    text = await get_content("catalog")
    await message.answer(text, disable_web_page_preview=True)

@client_router.message(F.text == SECTION_NAMES["about_shop"])
async def about_shop(message: Message):
    text = await get_content("about_shop")
    await message.answer(text)

@client_router.message(F.text == SECTION_NAMES["faq"])
async def faq(message: Message):
    text = await get_content("faq")
    await message.answer(text)