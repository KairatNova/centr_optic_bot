from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

class PrivateChatOnlyMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        # Проверяем только сообщения и callback-запросы
        if isinstance(event, (Message, CallbackQuery)):
            chat = event.chat if isinstance(event, Message) else event.message.chat if event.message else None

            if chat and chat.type != "private":

                return

        return await handler(event, data)