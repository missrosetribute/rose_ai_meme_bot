#!/usr/bin/env python3
"""
Rose AI Meme Bot - Group Chat Version
- Triggered by /meme <prompt> command
- 180 second per-user cooldown
- Fully async so multiple users can generate simultaneously
- Status messages are deleted after image is sent
- Binds to port 10000 to satisfy Render's web service port scan
"""

import logging
import asyncio
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from concurrent.futures import ThreadPoolExecutor
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

# Dedicated thread pool for image generation tasks
executor = ThreadPoolExecutor(max_workers=4)

# Per-user cooldown tracking: {user_id: last_used_timestamp}
COOLDOWN_SECONDS = 180

# Generation timeout in seconds
GENERATION_TIMEOUT = 120

user_cooldowns: dict[int, float] = {}


# ── Render health check server ─────────────────────────────────────────────────

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass  # Suppress HTTP access logs


def start_health_server():
    port = int(os.getenv('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    logger.info(f"Health check server listening on port {port}")
    server.serve_forever()


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_cooldown_remaining(user_id: int) -> int:
    last_used = user_cooldowns.get(user_id, 0)
    elapsed = time.time() - last_used
    remaining = COOLDOWN_SECONDS - elapsed
    return max(0, int(remaining))


async def delete_message_quietly(message) -> None:
    try:
        await message.delete()
    except BadRequest:
        pass


async def run_in_executor(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, func, *args)


# ── Command handlers ───────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    welcome_text = """🌹 *Rose AI Meme Generator* 🌹

Use `/meme <your prompt>` to create a unique Rose meme!

*Examples:*
• `/meme Rose at the gym`
• `/meme Rose as a detective`
• `/meme Rose trading crypto`
• `/meme Rose at a beach party`

"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')


async def meme_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id

    # Check cooldown
    remaining = get_cooldown_remaining(user_id)
    if remaining > 0:
        cooldown_msg = await update.message.reply_text(
            f"⏳ {user.first_name}, please wait {remaining}s before generating another meme."
        )
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

    status_msg = await update.message.reply_text(
        f"✨ Generating your meme, don't run away!",
        parse_mode='Markdown'
    )

    try:
        async def generate():
            caption = await run_in_executor(generate_caption, prompt)
            logger.info(f"[{user.first_name}] Caption: {caption}")

            rose_image = await run_in_executor(rose_gen.generate_rose_image, prompt, caption)
            logger.info(f"[{user.first_name}] Rose image generated")

            meme_image = await run_in_executor(rose_gen.compose_meme, rose_image, caption)
            return caption, meme_image

        caption, meme_image = await asyncio.wait_for(generate(), timeout=GENERATION_TIMEOUT)

        await delete_message_quietly(status_msg)

        await update.message.reply_photo(
            photo=meme_image,
            caption=f"🌹 *{user.first_name}'s Meme* 🌹\n\n💬 {caption}",
            parse_mode='Markdown'
        )

      
    except asyncio.TimeoutError:
        logger.error(f"Generation timed out for {user.first_name} after {GENERATION_TIMEOUT}s")
        await delete_message_quietly(status_msg)
        error_msg = await update.message.reply_text(
            "⏱️ Meme generation timed out — the image service is busy. Try again in a moment!"
        )
        await asyncio.sleep(6)
        await delete_message_quietly(error_msg)
        user_cooldowns.pop(user_id, None)

    except Exception as e:
        logger.error(f"Error generating meme for {user.first_name}: {e}")
        await delete_message_quietly(status_msg)
        error_msg = await update.message.reply_text(
            "❌ Something went wrong generating your meme. Try again!"
        )
        await asyncio.sleep(5)
        await delete_message_quietly(error_msg)
        user_cooldowns.pop(user_id, None)


def generate_caption(prompt: str) -> str:
    system_prompt = """You are a meme caption generator for Rose, a confident, sexy and sassy female.

Rose characteristics:
- Orange/red wavy hair with green hair accessory
- Vintage retro pinup aesthetic
- Confident, flirty, sassy personality
- Can be in any situation/outfit

Your job: If the prompt provides a caption you must use it for the meme being generated.
If no caption is provided then create a SHORT, FUNNY meme caption based on the user's prompt. No emojis.

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


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    logger.error(f"Error: {context.error}")


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    # Start health check server in a background thread so Render sees an open port
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("meme", meme_command))
    app.add_error_handler(error_handler)

    logger.info("🌹 Rose AI Meme Bot started (group chat mode)!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
