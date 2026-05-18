#!/usr/bin/env python3
"""
Rose AI Meme Bot - Group Chat Version
- Triggered by /meme <prompt> command
- 180 second per-user cooldown
- Fully async so multiple users can generate simultaneously
- Status messages are deleted after image is sent
- No buttons - clean simple interface
- gpt-image-1 handles all caption placement dynamically
- Graceful shutdown on SIGTERM (for Render deployments)
"""

import logging
import asyncio
import time
import threading
import signal
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from concurrent.futures import ThreadPoolExecutor
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
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

# Global app reference for shutdown
app_instance = None


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


# ── Graceful shutdown ──────────────────────────────────────────────────────────

def signal_handler(sig, frame):
    """Handle shutdown signals gracefully - called by Render before killing instance"""
    logger.info("🛑 Received shutdown signal, closing gracefully...")
    if app_instance:
        app_instance.stop()
    executor.shutdown(wait=False)
    logger.info("✅ Bot shut down cleanly")
    sys.exit(0)


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
        f"✨ Generating your meme...don't run away! 😘"
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

        # Send image - caption is already integrated by gpt-image-1
        await update.message.reply_photo(
            photo=meme_image,
            caption=f"🌹 *{user.first_name}'s Rose Meme* 🌹"
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
    """Generate a short, punchy caption for the meme."""
    system_prompt = """You are a meme caption generator for Rose, a confident, sassy female character.

Rose characteristics:
- Orange/red wavy hair with green bow
- Vintage retro pinup aesthetic
- Confident, flirty, sassy personality

Your job: Create a SHORT, FUNNY meme caption based on the user's prompt.
ONLY create a caption if the prompt does NOT provide one.
Examples of a specific caption request could be:
- Caption must say NO FUD ALLOWED
- Add the words "Everything will be fine" to the meme
- Make Rose say I love big green candles

Requirements:
- Keep it SHORT (30-100 characters)
- No emojis
- Make it FUNNY and shareable
- Can be 1-2 lines (use \\n for line breaks if needed)
- Appropriate for the meme context
- Works with Rose in any outfit/situation

Return ONLY the caption text. Nothing else."""

    message = anthropic_client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=150,
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
    global app_instance
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start health check server in a background thread so Render sees an open port
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()

    app_instance = Application.builder().token(TELEGRAM_TOKEN).build()

    app_instance.add_handler(CommandHandler("start", start))
    app_instance.add_handler(CommandHandler("help", help_command))
    app_instance.add_handler(CommandHandler("meme", meme_command))
    app_instance.add_error_handler(error_handler)

    logger.info("🌹 Rose AI Meme Bot started (group chat mode, no buttons)!")
    app_instance.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
