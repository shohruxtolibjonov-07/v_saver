"""Start, help, terms, and report command handlers."""

from aiogram import Router, types
from aiogram.filters import CommandStart, Command

from utils.messages import WELCOME, HELP, TERMS_OF_SERVICE, REPORT_INFO

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    """Handle /start command."""
    await message.answer(WELCOME, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Handle /help command."""
    await message.answer(HELP, parse_mode="HTML")


@router.message(Command("terms"))
async def cmd_terms(message: types.Message):
    """Handle /terms command — show Terms of Service."""
    await message.answer(TERMS_OF_SERVICE, parse_mode="HTML")


@router.message(Command("report"))
async def cmd_report(message: types.Message):
    """Handle /report command — copyright reporting instructions."""
    await message.answer(REPORT_INFO, parse_mode="HTML")
