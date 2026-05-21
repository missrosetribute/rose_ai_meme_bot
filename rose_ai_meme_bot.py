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

# Queue and task tracking — initialized in main() inside the event loop
request_queue: dict[int, int] = {}   # {user_id: queue_position}
active_tasks: set[int] = set()       # {user_ids with active tasks}
queue_lock: asyncio.Lock = None      # Created inside event loop in main()
queue_counter = 0                    # Increments per request
max_concurrent_tasks = 4             # Max tasks running simultaneously


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


# ── Queue Management ───────────────────────────────────────────────────────────

async def add_to_queue(user_id: int) -> int:
    """Add user to queue and return their actual position among pending requests."""
    global queue_counter
    async with queue_lock:
        queue_counter += 1
        request_queue[user_id] = queue_counter
        # Real position = how many entries are in the queue right now
        position = len(request_queue)
        logger.info(f"User {user_id} added to queue, position {position}")
        logger.info(f"Queue state: {request_queue}, Active tasks: {active_tasks}")
        return position


async def wait_for_task_slot() -> None:
    """Wait until there's a free task slot."""
    while True:
        async with queue_lock:
            if len(active_tasks) < max_concurrent_tasks:
                return
        await asyncio.sleep(0.5)


async def start_task(user_id: int) -> None:
    """Mark a task as active."""
    async with queue_lock:
        active_tasks.add(user_id)
        logger.info(f"Task started for user {user_id}. Active tasks: {len(active_tasks)}")


async def complete_task(user_id: int) -> None:
    """Mark a task as complete and remove from queue."""
    async with queue_lock:
        active_tasks.discard(user_id)
        request_queue.pop(user_id, None)
        logger.info(f"Task completed for user {user_id}. Active tasks: {len(active_tasks)}")
        logger.info(f"Queue state: {request_queue}, Active tasks: {active_tasks}")


def get_queue_stats() -> tuple[int, int]:
    """Get current queue size and active task count (non-blocking snapshot)."""
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
    except Exception as e:
        logger.warning(f"Could not delete message: {e}")


async def run_in_executor(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, func, *args)


# ── Caption Generation ─────────────────────────────────────────────────────────

def generate_caption(prompt: str) -> str:
    """Return user-specified caption, generated caption, or empty string for no caption."""
    upper = prompt.upper()

    # Explicit no-caption request
    if "NOCAPTION" in upper or "NO_CAPTION" in upper or "NO CAPTION" in upper:
        logger.info("User requested no caption")
        return ""

    # Explicit caption override
    if "CAPTION:" in upper:
        idx = upper.index("CAPTION:") + len("CAPTION:")
        caption = prompt[idx:].strip()
        if caption:
            caption = caption.replace('\\n', '\n')
            logger.info(f"Using user-supplied caption: {caption!r}")
            return caption

    # Generate caption with Claude
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

*Caption Options:*
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
    """Handle /meme command - vintage pinup Rose."""
    await _handle_meme_request(update, context, style='vintage')


async def ogmeme_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ogmeme command - original bot Rose."""
    await _handle_meme_request(update, context, style='og')


async def _handle_meme_request(update: Update, context: ContextTypes.DEFAULT_TYPE, style: str) -> None:
    """Shared handler logic for both /meme and /ogmeme commands."""
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
        cmd = "meme" if style == "vintage" else "ogmeme"
        usage_msg = await update.message.reply_text(
            f"❓ Please provide a prompt!\nExample: `/{cmd} Rose at the gym`",
            parse_mode='Markdown'
        )
        await asyncio.sleep(5)
        await delete_message_quietly(usage_msg)
        return

    # Mark cooldown immediately
    user_cooldowns[user_id] = time.time()

    # Add to queue and get position
    queue_position = await add_to_queue(user_id)
    _, active_count = get_queue_stats()

    # Inform user of their position
    if queue_position == 1 and active_count <= 1:
        queue_msg = await update.message.reply_text(
            "⏳ Your meme is generating now...\n\n🌹 You're up!"
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

    # Wait for a free slot then kick off generation
    await wait_for_task_slot()
    await start_task(user_id)

    asyncio.create_task(
        process_meme_generation(user, prompt, queue_msg, style)
    )


async def process_meme_generation(user, prompt: str, status_msg, style: str) -> None:
    """Process meme generation in background without blocking other commands."""
    user_id = user.id

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

        try:
            await status_msg.chat.send_photo(
                photo=meme_image,
                caption=f"🌹 *{user.first_name}'s Rose Meme* 🌹",
                parse_mode='Markdown'
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
        logger.error(f"Error generating meme for {user.first_name}: {e}", exc_info=True)
        await delete_message_quietly(status_msg)
        error_msg = await status_msg.reply_text(
            f"❌ Something went wrong generating your meme: {str(e)[:50]}"
        )
        await asyncio.sleep(5)
        await delete_message_quietly(error_msg)

    finally:
        await complete_task(user_id)
        logger.info(f"[{user.first_name}] Task marked complete, queue updated")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = """🌹 *Rose AI Meme Generator - Troubleshooting* 🌹

*My meme failed or was rejected*
Prompts that are sexual, violent, or otherwise inappropriate are automatically moderated by AI and will fail. Keep prompts fun and safe.

*Custom captions*
By default, the AI writes a caption based on your prompt. To set your own exact caption, add `CAPTION:` followed by your text:
`/ogmeme Rose at the gym CAPTION: No pain no gain`
`/meme Rose trading crypto CAPTION: We are so back`
Without `CAPTION:` the AI will write one for you. For image only without any caption, add `NOCAPTION`.

*Cooldown*
Each user has a 3-minute cooldown between memes. If you see a wait message, sit tight.

*Queue*
Busy times may add around 60s per queued request.

*My meme timed out*
The image service occasionally gets busy. Wait a moment and try again.

*Tips for better memes*
• Be specific: "Rose as a 1980s stockbroker" beats "Rose at work"
• Describe an outfit or setting for more variety
• Shorter captions look better on the image
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Unhandled error: {context.error}", exc_info=context.error)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    global app_instance, meme_generators, queue_lock

    # Create queue lock here so it's tied to the correct event loop
    queue_lock = asyncio.Lock()

    # Start health check server in background thread
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
        logger.error(f"❌ Failed to initialize generators: {e}", exc_info=True)
        sys.exit(1)

    app_instance = Application.builder().token(TELEGRAM_TOKEN).build()

    app_instance.add_handler(CommandHandler("start", start))
    app_instance.add_handler(CommandHandler("help", help_command))
    app_instance.add_handler(CommandHandler("meme", meme_command))
    app_instance.add_handler(CommandHandler("ogmeme", ogmeme_command))
    app_instance.add_error_handler(error_handler)

    logger.info("🌹 Rose AI Meme Bot started (vintage + OG styles, queue system enabled)!")

    # Let PTB handle SIGTERM/SIGINT cleanly — no manual signal.signal() needed
    app_instance.run_polling(
        allowed_updates=Update.ALL_TYPES,
        stop_signals=[signal.SIGTERM, signal.SIGINT],
    )

    # Clean up thread pool after polling stops
    executor.shutdown(wait=False)
    logger.info("✅ Bot shut down cleanly")


if __name__ == '__main__':
    main()
