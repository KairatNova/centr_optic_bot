from aiogram import Bot
from aiogram.types import Message, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup

from config import SECTION_NAMES



# Ваша основная клиентская клавиатура (из предыдущего примера)
def get_client_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=SECTION_NAMES["appointment"]),
                KeyboardButton(text=SECTION_NAMES["shop_address"])
            ],
            [
                KeyboardButton(text=SECTION_NAMES["promotions"]),
                KeyboardButton(text=SECTION_NAMES["catalog"])
            ],
            [
                KeyboardButton(text=SECTION_NAMES["about_shop"]),
                KeyboardButton(text=SECTION_NAMES["faq"])
            ]
        ],
        resize_keyboard=True, 
    )


from aiogram.types import BotCommand

async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="button", description=" Показать клавиатуру"),
    ]
    await bot.set_my_commands(commands)