#!/usr/bin/env python3
"""
Rose AI Meme Bot - Simple Telegram Bot
Users send prompts → Claude generates unique meme captions → Bot creates memes with Rose avatar
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
from meme_generator import MemeGenerator
import os

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize bot components
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
meme_gen = MemeGenerator(rose_image_path="rose_avatar.png")
anthropic_client = anthropic.Anthropic()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message"""
    welcome_text = """🌹 **Rose AI Meme Generator** 🌹

Just send me a description or idea, and I'll create a unique meme about it!

**Examples:**
• "when the chart pumps 🚀"
• "Rose moderating chat"
• "buying the dip"
• "hodling $ROSE"
• Any idea you want turned into a meme!

Each meme is AI-generated and completely unique.

*Powered by Claude AI*
"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def generate_meme(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate meme from user's prompt"""
    user_prompt = update.message.text
    
    try:
        await update.message.chat.send_action("upload_photo")
        await update.message.reply_text("✨ Creating your meme...")
        
        # Step 1: Use Claude to generate meme caption
        caption = generate_caption(user_prompt)
        
        # Step 2: Create meme image with caption + Rose avatar
        meme_image = meme_gen.create_meme(caption)
        
        # Step 3: Send to user
        await update.message.reply_photo(
            photo=meme_image,
            caption=f"Your meme for: *{user_prompt}*",
            parse_mode='Markdown'
        )
        
        # Add action buttons
        keyboard = [
            [
                InlineKeyboardButton("😂 Great!", callback_data="good"),
                InlineKeyboardButton("🔄 New Meme", callback_data="regen"),
            ]
        ]
        await update.message.reply_text(
            "Like it?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(
            "❌ Oops! Something went wrong. Try another prompt!"
        )

def generate_caption(prompt):
    """Use Claude to generate meme caption from user prompt"""
    
    system_prompt = """You are a meme caption generator. Create short, funny meme text based on the user's prompt.

The meme will feature Rose - a confident, sassy bot with retro pinup energy.

Requirements:
- Keep it SHORT (50-150 characters)
- Make it FUNNY and shareable
- Can be one or two lines (use \\n for line breaks)
- Match Rose's sassy, confident vibe
- Should work as a meme caption

Return ONLY the caption text, nothing else."""

    message = anthropic_client.messages.create(
        model="claude-opus-4-20250514",
        max_tokens=200,
        system=system_prompt,
        messages=[
            {"role": "user", "content": f"Create a meme caption for: {prompt}"}
        ]
    )
    
    caption = message.content[0].text.strip()
    # Convert escaped newlines
    caption = caption.replace('\\n', '\n')
    return caption

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button clicks"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "regen":
        await query.edit_message_text("Send another prompt! 🎨")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help message"""
    help_text = """🌹 **How to Use** 🌹

Simply send me any prompt or description, and I'll turn it into a meme!

**What works best:**
- Market moments ("when $ROSE pumps")
- Community jokes ("Rose moderation")
- Token ideas ("hodling through volatility")
- Any funny idea!

Each meme is unique and AI-generated.
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
    
    logger.info("🌹 Rose AI Meme Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
