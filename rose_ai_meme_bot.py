#!/usr/bin/env python3
"""
Rose AI Meme Bot - Group Chat Version
- Triggered by /meme <prompt> command
- 180 second per-user cooldown
- Fully async so multiple users can generate simultaneously
- Status messages are deleted after image is sent
"""

import logging
import asyncio
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.error import BadRequest
import anthropic
from image_generator import RoseImageGenerator
import os

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize bot components
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
rose_gen = RoseImageGenerator()
anthropic_client = anthropic.Anthropic()

# Per-user cooldown tracking: {user_id: last_used_timestamp}
COOLDOWN_SECONDS = 180
user_cooldowns: dict[int, float] = {}


def get_cooldown_remaining(user_id: int) -> int:
    """Returns seconds remaining on cooldown, or 0 if ready."""
    last_used = user_cooldowns.get(user_id, 0)
    elapsed = time.time() - last_used
    remaining = COOLDOWN_SECONDS - elapsed
    return max(0, int(remaining))


async def delete_message_quietly(message) -> None:
    """Delete a message, ignoring errors if it's already gone."""
    try:
        await message.delete()
    except BadRequest:
        pass


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message"""
    welcome_text = """🌹 *Rose AI Meme Generator* 🌹

Use `/meme <your prompt>` to create a unique Miss Rose meme!

*Examples:*
• `/meme Rose at the gym`
• `/meme Rose as a detective`
• `/meme Rose trading crypto`
• `/meme Rose at a beach party`

"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')


async def meme_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /meme <prompt> command.
    - Checks cooldown before doing anything
    - Sends a status message, generates async, then deletes the status message
    - Multiple users can generate simultaneously
    """
    user = update.effective_user
    user_id = user.id

    # Check cooldown
    remaining = get_cooldown_remaining(user_id)
    if remaining > 0:
        cooldown_msg = await update.message.reply_text(
            f"⏳ {user.first_name}, please wait {remaining}s before generating another meme."
        )
        # Auto-delete the cooldown notice after 5 seconds
        await asyncio.sleep(5)
        await delete_message_quietly(cooldown_msg)
        return

    # Check prompt was provided
    prompt = " ".join(context.args).strip()
    if not prompt:
        usage_msg = await update.message.reply_text(
            "❓ Please provide a prompt!\nExample: `/meme Rose at the gym`",
            parse_mode='Markdown'
        )
        await asyncio.sleep(5)
        await delete_message_quietly(usage_msg)
        return

    # Mark cooldown immediately so user can't spam while generating
    user_cooldowns[user_id] = time.time()

    # Send status message (will be deleted after image is sent)
    status_msg = await update.message.reply_text(
        f"✨ Generating your meme for: _{prompt}_...",
        parse_mode='Markdown'
    )

    try:
        # Run blocking generation in a thread so other users aren't blocked
        loop = asyncio.get_event_loop()

        caption = await loop.run_in_executor(None, generate_caption, prompt)
        logger.info(f"[{user.first_name}] Caption: {caption}")

        rose_image = await loop.run_in_executor(
            None, rose_gen.generate_rose_image, prompt, caption
        )
        logger.info(f"[{user.first_name}] Rose image generated")

        meme_image = await loop.run_in_executor(
            None, rose_gen.compose_meme, rose_image, caption
        )

        # Delete status message before sending the result
        await delete_message_quietly(status_msg)

        # Send the meme
        await update.message.reply_photo(
            photo=meme_image,
            caption=f"🌹 *{user.first_name}'s Meme* 🌹\n\n_{prompt}_\n\n💬 {caption}",
            parse_mode='Markdown'
        )

        # Add action buttons
        keyboard = [
            [
                InlineKeyboardButton("😂 Love it!", callback_data="good"),
                InlineKeyboardButton("🔄 New Meme", callback_data=f"regen:{prompt}"),
            ]
        ]
        await update.message.reply_text(
            "Like your meme?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(f"Error generating meme for {user.first_name}: {e}")
        await delete_message_quietly(status_msg)
        error_msg = await update.message.reply_text(
            "❌ Something went wrong generating your meme. Try again!"
        )
        await asyncio.sleep(5)
        await delete_message_quietly(error_msg)

        # Reset cooldown on failure so user can try again immediately
        user_cooldowns.pop(user_id, None)


def generate_caption(prompt: str) -> str:
    """Use Claude to generate a meme caption from user prompt."""
    system_prompt = """You are a meme caption generator for Rose, a confident and sassy female.

Rose characteristics:
- Orange/red wavy hair with green hair accessory
- Vintage retro pinup aesthetic
- Confident, flirty, sassy personality
- Can be in any situation/outfit

Your job: Create a SHORT, FUNNY meme caption based on the user's prompt.

Requirements:
- Keep it SHORT (50-150 characters)
- Make it FUNNY and shareable
- Can be 1-2 lines (use \\n for line breaks)
- Appropriate for the meme context
- Works with Rose in any outfit/situation

Return ONLY the caption text. Nothing else."""

    message = anthropic_client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=200,
        system=system_prompt,
        messages=[
            {"role": "user", "content": f"Create a meme caption for: {prompt}"}
        ]
    )

    caption = message.content[0].text.strip()
    caption = caption.replace('\\n', '\n')
    return caption


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button clicks."""
    query = update.callback_query
    await query.answer()

    if query.data.startswith("regen:"):
        prompt = query.data.split("regen:", 1)[1]
        await query.edit_message_text(
            f"Send another prompt to generate a new one! 🎨",
            parse_mode='Markdown'
        )
    elif query.data == "good":
        await query.answer("Glad you love it! 🌹", show_alert=False)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help message"""
    help_text = """🌹 *Rose AI Meme Generator Help* 🌹

*Command:* `/meme <your prompt>`

*Examples:*
• `/meme Rose as a CEO` → Rose in a power suit
• `/meme Rose at the beach` → Rose in a beach outfit
• `/meme Rose playing guitar` → Rose with an instrument
• `/meme Rose cooking` → Rose in the kitchen

"""
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors."""
    logger.error(f"Error: {context.error}")


def main():
    """Start the bot."""
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("meme", meme_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_error_handler(error_handler)

    logger.info("🌹 Rose AI Meme Bot started (group chat mode)!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
