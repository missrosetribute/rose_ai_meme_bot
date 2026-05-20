#!/usr/bin/env python3
"""
Rose AI Meme Bot - Group Chat Version with Queue System and Two Styles
- /meme command → Vintage pinup Rose
- /ogmeme command → Original bot Rose
- Request queue system with task completion tracking
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
from og_image_generator import OGRoseImageGenerator
import os

# Validate required env vars on startup
required_vars = ['TELEGRAM_TOKEN', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY']
missing = [v for v in required_vars if not os.getenv(v)]
if missing:
    print(f"❌ STARTUP FAILED - Missing env vars: {missing}")
    sys.exit(1)

print("✅ All env vars present")
print(f"✅ TELEGRAM_TOKEN starts with: {os.getenv('TELEGRAM_TOKEN')[:10]}...")

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize bot components
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
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

# Meme generators (initialized in main)
meme_generators = {}

# Queue and task tracking
request_queue: dict[int, int] = {}  # {user_id: queue_position}
active_tasks: set[int] = set()      # {user_ids with active tasks}
queue_lock = asyncio.Lock()         # Thread-safe lock
queue_counter = 0                   # Position counter
max_concurrent_tasks = 4            # Max tasks running simultaneously


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
    """Handle shutdown signals gracefully"""
    logger.info("🛑 Received shutdown signal, closing gracefully...")
    if app_instance:
        app_instance.stop()
    executor.shutdown(wait=False)
    logger.info("✅ Bot shut down cleanly")
    sys.exit(0)


# ── Queue Management ───────────────────────────────────────────────────────────

async def add_to_queue(user_id: int) -> int:
    """Add user to queue and return their position"""
    global queue_counter
    async with queue_lock:
        queue_counter += 1
        position = queue_counter
        request_queue[user_id] = position
        logger.info(f"User {user_id} added to queue at position {position}")
        logger.info(f"Queue state: {request_queue}, Active tasks: {active_tasks}")
        return position


async def get_queue_position(user_id: int) -> int:
    """Get current position in queue"""
    async with queue_lock:
        return request_queue.get(user_id, 0)


async def wait_for_task_slot() -> None:
    """Wait until there's a free task slot"""
    while True:
        async with queue_lock:
            if len(active_tasks) < max_concurrent_tasks:
                return
        await asyncio.sleep(0.1)


async def start_task(user_id: int) -> None:
    """Mark a task as active"""
    async with queue_lock:
        active_tasks.add(user_id)
        logger.info(f"Task started for user {user_id}. Active tasks: {len(active_tasks)}")


async def complete_task(user_id: int) -> None:
    """Mark a task as complete and update queue"""
    async with queue_lock:
        active_tasks.discard(user_id)
        if user_id in request_queue:
            del request_queue[user_id]
        logger.info(f"Task completed for user {user_id}. Active tasks: {len(active_tasks)}")
        logger.info(f"Queue state: {request_queue}, Active tasks: {active_tasks}")


def get_queue_stats() -> tuple[int, int]:
    """Get current queue and active task counts (non-blocking read)"""
    return len(request_queue), len(active_tasks)


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


# ── Caption Generation ─────────────────────────────────────────────────────────

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
- Orange/red wavy hair with green bow
- Vintage retro pinup aesthetic
- Confident, flirty, sassy personality

Your job: Create a SHORT, FUNNY meme caption based on the user's prompt.

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


# ── Command handlers ───────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    welcome_text = """🌹 *Rose AI Meme Generator* 🌹

Choose your Rose style!

`/meme <prompt>` - Vintage pinup Rose (retro 1950s)
`/ogmeme <prompt>` - Original bot Rose (colorful modern)

**Caption Options:**
• Auto caption: Just your prompt
• Custom caption: Add `CAPTION: Your text`
• No caption: Add `NOCAPTION`

*Examples:*
• `/meme Rose trading crypto`
• `/meme Rose at gym CAPTION: Gains & Roses`
• `/ogmeme Rose party NOCAPTION`

Each meme is unique!
"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')


async def meme_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /meme command - vintage pinup Rose"""
    await _handle_meme_request(update, context, style='vintage')


async def ogmeme_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ogmeme command - original bot Rose"""
    await _handle_meme_request(update, context, style='og')


async def _handle_meme_request(update: Update, context: ContextTypes.DEFAULT_TYPE, style: str) -> None:
    """Shared handler logic for both /meme and /ogmeme commands"""
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
            f"❓ Please provide a prompt!\nExample: `/{'' if style == 'vintage' else 'og'}meme Rose at the gym`",
            parse_mode='Markdown'
        )
        await asyncio.sleep(5)
        await delete_message_quietly(usage_msg)
        return

    # Mark cooldown immediately
    user_cooldowns[user_id] = time.time()

    # Add to queue and get position
    queue_position = await add_to_queue(user_id)
    queue_size, active_count = get_queue_stats()

    # Tell user their queue position
    if queue_position == 1 and active_count == 0:
        queue_msg = await update.message.reply_text(
            f"⏳ Your meme is generating now...\n\n🌹 You're up!"
        )
    else:
        est_wait = (queue_position - 1) * 30
        queue_msg = await update.message.reply_text(
            f"📋 Your meme request is in the queue!\n\n"
            f"Position: #{queue_position}\n"
            f"Ahead of you: {queue_position - 1}\n"
            f"Currently processing: {active_count}\n\n"
            f"⏳ Estimated wait: ~{est_wait}s"
        )

    # Wait for a free task slot
    await wait_for_task_slot()

    # Mark task as active
    await start_task(user_id)

    # Process in background (non-blocking)
    asyncio.create_task(
        process_meme_generation(user, prompt, queue_msg, style)
    )


async def process_meme_generation(user, prompt: str, status_msg, style: str) -> None:
    """Process meme generation in background without blocking other commands"""
    user_id = user.id
    
    # Get the right generator
    generator = meme_generators.get(style)
    if not generator:
        logger.error(f"No generator found for style: {style}")
        await delete_message_quietly(status_msg)
        await status_msg.reply_text("❌ Error: Meme style not available")
        await complete_task(user_id)
        return
    
    try:
        async def generate():
            caption = await run_in_executor(generate_caption, prompt)
            logger.info(f"[{user.first_name}] Caption: {caption!r}")

            rose_image = await run_in_executor(generator.generate_rose_image, prompt, caption)
            logger.info(f"[{user.first_name}] {style.upper()} Rose image generated")

            meme_image = await run_in_executor(generator.compose_meme, rose_image, caption)
            return caption, meme_image

        caption, meme_image = await asyncio.wait_for(generate(), timeout=GENERATION_TIMEOUT)

        await delete_message_quietly(status_msg)

        # Send image
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
        # Always mark task complete to close the loop
        await complete_task(user_id)
        logger.info(f"[{user.first_name}] Task marked complete, queue updated")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = """🌹 *Rose AI Meme Generator Help* 🌹

**Two Rose Styles:**
• `/meme <prompt>` → Vintage pinup Rose (retro 1950s style)
• `/ogmeme <prompt>` → Original bot Rose (colorful modern style)

**Caption Control:**
• No args: Claude generates funny caption
• `CAPTION: text` → Your custom caption
• `NOCAPTION` → No caption at all

**Examples:**
• `/meme Rose as a CEO`
• `/meme Rose at beach CAPTION: Sun & Sass`
• `/ogmeme Rose party NOCAPTION`
• `/ogmeme Rose trading crypto`

Each meme is unique with dynamically placed text!
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Error: {context.error}")


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    global app_instance, meme_generators
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start health check server in background
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()

    # Initialize both Rose generators
    try:
        vintage_gen = RoseImageGenerator()
        og_gen = OGRoseImageGenerator()
        meme_generators = {
            'vintage': vintage_gen,
            'og': og_gen
        }
        logger.info("✅ Both Rose generators initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize generators: {e}")
        sys.exit(1)

    app_instance = Application.builder().token(TELEGRAM_TOKEN).build()

    app_instance.add_handler(CommandHandler("start", start))
    app_instance.add_handler(CommandHandler("help", help_command))
    app_instance.add_handler(CommandHandler("meme", meme_command))
    app_instance.add_handler(CommandHandler("ogmeme", ogmeme_command))
    app_instance.add_error_handler(error_handler)

    logger.info("🌹 Rose AI Meme Bot started (vintage + OG styles, queue system enabled)!")
    app_instance.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
