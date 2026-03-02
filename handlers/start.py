from aiogram import Router, types
from aiogram.filters import CommandStart, Command

from utils.messages import WELCOME, HELP

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    """Handle /start command."""
    await message.answer(WELCOME, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Handle /help command."""
    await message.answer(HELP, parse_mode="HTML")
