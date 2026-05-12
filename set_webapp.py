import asyncio
from aiogram import Bot
from aiogram.types import MenuButtonWebApp, WebAppInfo
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def main():
    bot = Bot(token=BOT_TOKEN)
    url = "https://somlyai-project-production.up.railway.app"
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Ochish", web_app=WebAppInfo(url=url))
        )
        print("OK - Web App tugmasi muvaffaqiyatli o'rnatildi!")
    except Exception as e:
        print(f"XATO: {str(e)}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
