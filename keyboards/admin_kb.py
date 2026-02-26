from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton


def get_admin_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Клиенты и рецепты", callback_data="admin_clients")],
        [InlineKeyboardButton(text="📨 Рассылка одному пользователю", callback_data="admin_message_one")],
        [InlineKeyboardButton(text="◀ Выход из панели админа", callback_data="admin_exit")],
    ])