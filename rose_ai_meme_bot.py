#!/usr/bin/env python3
"""
Rose AI Meme Bot - Group Chat Version with Request Queuing
- Triggered by /meme <prompt> command or /ogmeme <prompt> command
- 180 second per-user cooldown
- Fully async with proper concurrent request handling
- Status messages are deleted after image is sent
- No buttons - clean simple interface
- gpt-image-1 handles all caption placement dynamically
- Graceful shutdown on SIGTERM (for Render deployments)
- QUEUE SYSTEM: Instantly replies that request is queued, processes in background
  Queue is an ordered list that shrinks as tasks complete and resets when empty
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
from og_image_generator import RoseImageGenerator
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

# Queue tracking: ordered list of user_ids
# Naturally resets to empty when all tasks complete
request_queue: list[int] = []
queue_lock = asyncio.Lock()


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


async def add_to_queue(user_id: int) -> int:
    """Add user to queue and return their 1-based position"""
    async with queue_lock:
        request_queue.append(user_id)
        position = len(request_queue)
        logger.info(f"User {user_id} added to queue at position {position}")
        return position


async def remove_from_queue(user_id: int) -> None:
    """Remove user from queue; list shrinks and resets to empty when all done"""
    async with queue_lock:
        if user_id in request_queue:
            request_queue.remove(user_id)
            logger.info(f"User {user_id} removed from queue. Queue size: {len(request_queue)}")


async def get_queue_size() -> int:
    """Get current number of pending requests"""
    async with queue_lock:
        return len(request_queue)


async def get_queue_position(user_id: int) -> int:
    """Get current 1-based position of user in queue, or 0 if not found"""
    async with queue_lock:
        try:
            return request_queue.index(user_id) + 1
        except ValueError:
            return 0


# ── Command handlers ───────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    welcome_text = """🌹 *Rose AI Meme Generator* 🌹

Use `/ogmeme <your prompt>` to create a unique OG styled Rose meme!
Use `/meme <your prompt>` to create a unique Vintage styled Rose meme!

*Examples:*
• `/ogmeme Rose at the gym`
• `/meme Rose as a detective`
• `/ogmeme Rose trading crypto`
• `/meme Rose at a beach party`

Use `/queue` to see how many requests are pending.
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
            "❓ Please provide a prompt!\nExample: `/ogmeme Rose at the gym`",
            parse_mode='Markdown'
        )
        await asyncio.sleep(5)
        await delete_message_quietly(usage_msg)
        return

    # Mark cooldown immediately so user can't spam while generating
    user_cooldowns[user_id] = time.time()

    # Add to queue and get position
    queue_position = await add_to_queue(user_id)

    # Immediately tell user their request is queued
    if queue_position == 1:
        queue_msg = await update.message.reply_text(
            "⏳ Your meme is generating now...don't run away! 😘"
        )
    else:
        queue_msg = await update.message.reply_text(
            f"📋 Your meme request is in the queue!\n\n"
            f"Position: #{queue_position}\n\n"
            f"⏳ Estimated wait: ~{(queue_position - 1) * 60}s"
        )

    # Process in background (non-blocking)
    asyncio.create_task(
        process_meme_generation(user, prompt, queue_msg)
    )


async def process_meme_generation(user, prompt: str, status_msg) -> None:
    """Process meme generation in background without blocking other commands"""
    user_id = user.id

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
        try:
            await status_msg.chat.send_photo(
                photo=meme_image,
                caption=f"🌹 *{user.first_name}'s Rose Meme* 🌹"
            )
        except Exception as e:
            logger.error(f"Error sending photo: {e}")
            await status_msg.reply_text("❌ Error sending meme!")

    except asyncio.TimeoutError:
        logger.error(f"Generation timed out for {user.first_name} after {GENERATION_TIMEOUT}s")
        await delete_message_quietly(status_msg)
        error_msg = await status_msg.reply_text(
            "⏱️ Meme generation timed out — the image service is busy. Try again in a moment!"
        )
        await asyncio.sleep(6)
        await delete_message_quietly(error_msg)

    except Exception as e:
        logger.error(f"Error generating meme for {user.first_name}: {e}")
        await delete_message_quietly(status_msg)
        error_msg = await status_msg.reply_text(
            f"❌ Something went wrong generating your meme: {str(e)[:50]}"
        )
        await asyncio.sleep(5)
        await delete_message_quietly(error_msg)

    finally:
        # Always remove from queue when done — list resets to [] when all tasks complete
        await remove_from_queue(user_id)
        logger.info(f"[{user.first_name}] Meme generation complete, removed from queue")


def generate_caption(prompt: str) -> str:
    """Return user-specified caption, generated caption, or empty string for no caption."""
    # Check for explicit NO CAPTION option: "NOCAPTION" or "NO_CAPTION"
    upper = prompt.upper()
    if "NOCAPTION" in upper or "NO_CAPTION" in upper or "NO CAPTION" in upper:
        logger.info("User requested no caption")
        return ""  # Return empty string = no caption
    
    # Check for explicit caption override: "CAPTION: <text>"
    if "CAPTION:" in upper:
        idx = upper.index("CAPTION:") + len("CAPTION:")
        caption = prompt[idx:].strip()
        if caption:
            caption = caption.replace('\\n', '\n')
            logger.info(f"Using user-supplied caption: {caption!r}")
            return caption
    
    # No caption provided — generate one with Claude
    system_prompt = """You are a meme caption generator for Rose, a confident, sassy female character.

Rose characteristics:
- Orange/red wavy hair with green bow or accessory
- Vintage retro pinup aesthetic
- Confident, flirty, sassy personality

Your job: Create a SHORT, FUNNY meme caption based on the user's prompt.
The user has NOT provided a caption, so invent one that fits the scene described.

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


async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current queue status to users"""
    size = await get_queue_size()
    if size == 0:
        await update.message.reply_text(
            "✅ Queue is empty — your meme will generate instantly!"
        )
    elif size == 1:
        await update.message.reply_text(
            "📋 *1 meme* is currently generating.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"📋 *{size} memes* are currently in the queue.\n\n"
            f"⏳ Estimated wait for a new request: ~{size * 60}s",
            parse_mode='Markdown'
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = """🌹 *Rose AI Meme Generator - Troubleshooting* 🌹

*My meme failed or was rejected*
Prompts that are sexual, violent, or otherwise inappropriate are automatically moderated by AI and will fail. Keep prompts fun and safe.

*Custom captions*
By default, the AI writes a caption based on your prompt. To set your own exact caption, add `CAPTION:` followed by your text:
`/ogmeme Rose at the gym CAPTION: No pain no gain`
`/meme Rose trading crypto CAPTION: We are so back`

Without `CAPTION:` the AI will write one for you. For image only without any caption, add 'NOCAPTION'.

*Cooldown*
Each user has a 3-minute cooldown between memes. If you see a wait message, sit tight.

*Queue*
Use `/queue` to see how many memes are currently generating. Busy times may add around 60s per queued request.

*My meme timed out*
The image service occasionally gets busy. Wait a moment and try again.

*Tips for better memes*
- Be specific: "Rose as a 1980s stockbroker" beats "Rose at work"
- Describe an outfit or setting for more variety
- Shorter captions look better on the image
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
    app_instance.add_handler(CommandHandler("ogmeme", ogmeme_command))
    app_instance.add_handler(CommandHandler("queue", queue_command))
    app_instance.add_error_handler(error_handler)

    logger.info("🌹 Rose AI Meme Bot started (group chat mode, queue system enabled)!")
    app_instance.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
