#!/usr/bin/env python3
"""
Rose AI Meme Bot - Telegram Bot with Dynamic Rose Image Generation
Users send prompts → Claude generates meme caption + Rose description → Creates unique meme
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

Send me any prompt, and I'll create a unique meme with Rose!

**How it works:**
1. You describe what you want
2. I generate a funny caption
3. I create Rose based on the context
4. You get a unique meme!

**Examples:**
• "Rose being a mod"
• "trading $ROSE gains"
• "Rose at a party"
• "Rose in business mode"
• Any situation you can think of!

Each meme has a dynamically created Rose - different outfit, pose, and style based on your prompt!

*Powered by Claude AI*
"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def generate_meme(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate meme from user's prompt"""
    user_prompt = update.message.text
    
    try:
        await update.message.chat.send_action("upload_photo")
        await update.message.reply_text("✨ Creating your unique meme...")
        
        # Step 1: Generate meme caption from prompt
        caption = generate_caption(user_prompt)
        
        # Step 2: Generate Rose description based on prompt + caption
        rose_description = rose_gen.generate_rose_description(user_prompt, caption)
        logger.info(f"Rose description: {rose_description}")
        
        # Step 3: Create meme with caption
        # (In production, you'd also generate the Rose image using the description)
        meme_image = rose_gen.create_visual_meme(rose_description, caption)
        
        # Step 4: Send to user
        await update.message.reply_photo(
            photo=meme_image,
            caption=f"*Your unique meme for:* {user_prompt}\n\n💬 {caption}",
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
    
    system_prompt = """You are a meme caption generator for Rose, a confident and sassy bot.

Rose has:
- Orange/red wavy hair with green bow
- Vintage retro pinup aesthetic
- Confident, flirty, sassy personality
- Can appear in any outfit or setting based on the meme context

Your job:
1. Understand the user's meme context
2. Generate a SHORT, FUNNY meme caption
3. Make it work with a dynamic Rose (who will look different each time)

Requirements:
- Keep it SHORT (50-150 characters)
- Make it FUNNY and shareable
- Can be one or two lines (use \\n for line breaks)
- The caption should work regardless of Rose's specific outfit/pose
- Works as a meme caption

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

Send any prompt describing a situation or context, and I'll create a unique meme with a dynamically generated Rose!

**The magic:**
- Your prompt → Claude creates funny caption
- Your prompt → Claude describes how Rose should look
- Rose is created fresh each time with relevant outfit and pose!

**Examples:**
- "Rose at the gym" → Rose in gym clothes, confident pose
- "Rose trading crypto" → Rose in business casual, focused
- "Rose at a concert" → Rose in party outfit, excited
- "Rose as a pirate" → Rose in pirate outfit, adventurous

Each meme is 100% unique!
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
