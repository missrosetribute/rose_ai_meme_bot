#!/usr/bin/env python3
"""
Rose Token AI Telegram Meme Generator Bot
Generates fresh, unique memes from prompts using Claude API
Uses Rose's image as character reference
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
import random
from meme_generator_ai import AIMemeGenerator
from config import TELEGRAM_TOKEN

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize AI meme generator
meme_gen = AIMemeGenerator(rose_image_path="rose_avatar.png")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    welcome_text = """🌹 **Welcome to Rose AI Meme Generator!** 🌹

I create completely fresh, unique memes powered by Claude AI!

**How to use:**
1️⃣ Send any message or idea
2️⃣ I'll generate a custom meme about it featuring Rose
3️⃣ Each meme is unique and personalized!

**Commands:**
/meme - Generate a random Rose meme idea
/help - Get help
/meme_cheeky - Generate sassy Rose meme
/meme_token - Generate $ROSE token meme
/meme_moderation - Generate Rose moderation meme

**Or just send me text** and I'll turn it into a meme!

Examples:
• "when the chart goes up" → Fresh meme!
• "Rose being a great moderator" → Fresh meme!
• "buying the dip" → Fresh meme!
• Any idea you have → Fresh meme! ✨

*Every meme is AI-generated and unique!*
"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def generate_from_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str = "general") -> None:
    """Generate a meme from user's text prompt"""
    user_text = update.message.text
    
    # Don't process bot commands
    if user_text.startswith('/'):
        return
    
    try:
        await update.message.chat.send_action("upload_photo")
        await update.message.reply_text("🎨 Creating fresh meme from your idea... ✨")
        
        # Generate meme using AI
        meme_image = meme_gen.generate_meme_from_prompt(user_text, category=category)
        
        # Send the meme
        await update.message.reply_photo(
            photo=meme_image,
            caption=f"✨ Your AI-Generated Rose Meme ✨\n\nPrompt: {user_text}",
            parse_mode='Markdown'
        )
        
        # Add reaction buttons
        keyboard = [
            [
                InlineKeyboardButton("😂 Funny", callback_data="react_funny"),
                InlineKeyboardButton("🔥 Fire", callback_data="react_fire"),
            ],
            [
                InlineKeyboardButton("🔄 Another Meme", callback_data="gen_new"),
                InlineKeyboardButton("📤 Share", callback_data="share"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("How'd you like it?", reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error generating meme: {e}")
        await update.message.reply_text(
            "🌹 Oops! Rose's AI hit a snag. Try a different prompt! 🌹"
        )

async def meme_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate a meme with a random Rose-themed prompt"""
    category = "general"
    
    # Check if user specified a category
    if context.args:
        arg = context.args[0].lower()
        if arg in ["cheeky", "token", "moderation"]:
            category = arg
    
    # Generate a fun prompt for Claude to work with
    prompts = {
        "moderation": [
            "Rose bot moderating chat perfectly",
            "When someone tries to spam Rose's chat",
            "Rose bot doing its job better than mods",
            "The power of Rose moderation",
            "Rose: guardian of the chat",
        ],
        "token": [
            "Buying $ROSE at the dip",
            "$ROSE chart going vertical",
            "Hodling $ROSE through volatility",
            "$ROSE community strength",
            "Rose token gains incoming",
        ],
        "cheeky": [
            "Rose feeling herself today",
            "Confidence level: Rose energy",
            "That feeling when Rose approves",
            "Rose bot got me like",
            "Swagger: Rose edition",
        ],
        "general": [
            "Rose being amazing",
            "Rose community vibes",
            "Rose bot magic",
            "Rose charm offensive",
            "Why we love Rose",
        ]
    }
    
    selected_prompts = prompts.get(category, prompts["general"])
    prompt = random.choice(selected_prompts)
    
    try:
        await update.message.chat.send_action("upload_photo")
        await update.message.reply_text("🎨 Generating fresh meme idea... ✨")
        
        # Generate meme
        meme_image = meme_gen.generate_meme_from_prompt(prompt, category=category)
        
        # Send meme
        await update.message.reply_photo(
            photo=meme_image,
            caption=f"✨ AI-Generated {category.capitalize()} Meme ✨\n\n_{prompt}_",
            parse_mode='Markdown'
        )
        
        keyboard = [
            [
                InlineKeyboardButton("😂 Funny", callback_data="react_funny"),
                InlineKeyboardButton("🔥 Fire", callback_data="react_fire"),
            ],
            [
                InlineKeyboardButton("🔄 Another Meme", callback_data="gen_new"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("How'd you like it?", reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("🌹 Rose's AI needs a moment to think... try again! 🌹")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button presses"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "gen_new":
        # Generate another meme with random prompt
        context.args = []
        await meme_command(query.message, context)
    elif query.data == "react_funny" or query.data == "react_fire":
        await query.edit_message_text("Thanks for enjoying the meme! 😄")
    elif query.data == "share":
        await query.edit_message_text(
            text="📤 Share this with your community!\n\n"
                 "Tag @rose_token and let them know you're spreading Rose vibes! 🌹"
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send help message"""
    help_text = """🌹 **Rose AI Meme Generator Help** 🌹

**How it works:**
I use Claude AI to generate fresh, unique memes from your prompts!
Rose's avatar is used as character reference for the meme style.

**Send me anything:**
• "Rose moderating chat" → Fresh meme!
• "Buying the dip" → Fresh meme!
• "$ROSE to the moon" → Fresh meme!
• Any idea → Fresh meme! ✨

**Commands:**
/meme - Random Rose meme
/meme_cheeky - Sassy Rose energy
/meme_token - $ROSE token meme
/meme_moderation - Rose moderation meme
/help - This message

**Pro tip:** The more specific your prompt, the better the meme!

Each meme is AI-generated and completely unique. No templates!

Made with 🌹 by Claude for the Rose community
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a message to notify the developer."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            "🌹 Something went wrong with Rose's AI! Try again in a moment."
        )

def main() -> None:
    """Start the bot"""
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("meme", meme_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Text messages (any user text becomes a meme prompt)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, 
                      lambda u, c: generate_from_prompt(u, c, "general"))
    )
    
    # Button callbacks
    application.add_handler(CallbackQueryHandler(button_callback))

    # Error handling
    application.add_error_handler(error_handler)

    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
