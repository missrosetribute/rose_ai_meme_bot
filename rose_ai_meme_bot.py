#!/usr/bin/env python3
"""
Rose AI Meme Bot - Dynamic Rose Image Generation
Claude (Anthropic) generates Rose descriptions + DALL-E 3 creates unique images
Best quality with minimal errors
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message"""
    welcome_text = """🌹 **Rose AI Meme Generator** 🌹

Send me any prompt, and I'll create a UNIQUE meme with a dynamically generated Rose!

**Try these prompts:**
• "Rose at the gym"
• "Rose as a detective"
• "Rose at a party"
• "Rose trading $ROSE"
• Any situation you imagine!

"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def generate_meme(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate meme from user's prompt"""
    user_prompt = update.message.text
    
    try:
        await update.message.chat.send_action("upload_photo")
        await update.message.reply_text("✨ Creating your unique meme 🎨")
        
        # Step 1: Generate meme caption from prompt
        caption = generate_caption(user_prompt)
        logger.info(f"Generated caption: {caption}")
        
        # Step 2: Generate Rose image based on prompt + caption
        rose_image = rose_gen.generate_rose_image(user_prompt, caption)
        logger.info(f"Generated Rose image")
        
        # Step 3: Compose final meme
        meme_image = rose_gen.compose_meme(rose_image, caption)
        
        # Step 4: Send to user
        await update.message.reply_photo(
            photo=meme_image,
            caption=f"🌹 *Your Unique Meme* 🌹\n\n_{user_prompt}_\n\n💬 {caption}",
            parse_mode='Markdown'
        )
        
        # Add action buttons
        keyboard = [
            [
                InlineKeyboardButton("😂 Love it!", callback_data="good"),
                InlineKeyboardButton("🔄 New Meme", callback_data="regen"),
            ]
        ]
        await update.message.reply_text(
            "Like your meme?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Error generating meme: {e}")
        await update.message.reply_text(
            "❌ Oops! Something went wrong. Try another prompt!"
        )

def generate_caption(prompt):
    """Use Claude to generate meme caption from user prompt"""
    
    system_prompt = """You are a meme caption generator for Rose, a confident and sassy bot.

Rose characteristics:
- Orange/red wavy hair with green bow
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
    """Handle button clicks"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "regen":
        await query.edit_message_text("Send another prompt to create a new meme! 🎨")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help message"""
    help_text = """🌹 **Rose AI Meme Generator Help** 🌹

**Send any prompt and I'll create a unique meme!**

Each meme has:
✨ Unique Rose image (generated just for your meme)
✨ Funny AI caption
✨ Contextual outfit/pose
✨ Perfect for sharing

The magic: Rose always looks like Rose, but she's created fresh each time based on YOUR prompt!
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Error handling"""
    logger.error(f"Error: {context.error}")

def main():
    """Start the bot"""
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generate_meme))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_error_handler(error_handler)
    
    logger.info("🌹 Rose AI Meme Bot started with Claude + DALL-E 3!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
