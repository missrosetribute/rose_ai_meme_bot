"""
AI-Powered Meme Generator
Generates fresh, creative memes using Claude API
Uses Rose's image as character reference for styling
Each meme is completely unique based on user prompts
"""

from PIL import Image, ImageDraw, ImageFont
import textwrap
import os
from io import BytesIO
import anthropic
import json

class AIMemeGenerator:
    def __init__(self, rose_image_path=None):
        """
        Initialize AI Meme Generator
        
        Args:
            rose_image_path: Path to Rose's avatar image (used as reference)
        """
        self.rose_image_path = rose_image_path or "rose_avatar.png"
        self.rose_image = self._load_rose_image()
        
        # Initialize Anthropic client (uses ANTHROPIC_API_KEY env var)
        self.client = anthropic.Anthropic()
        
        # Rose character reference for AI
        self.rose_character_prompt = """
        Rose is a confident, sassy bot with retro pinup aesthetic. She has:
        - Vibrant orange/red wavy hair
        - A signature green bow
        - A sass-filled attitude
        - Strong personality and humor
        - Often flirty and confident energy
        - Rose bot moderator vibe mixed with fun community energy
        """

    def _load_rose_image(self):
        """Load Rose bot avatar image as character reference"""
        try:
            if os.path.exists(self.rose_image_path):
                return Image.open(self.rose_image_path).convert("RGBA")
            else:
                return None
        except Exception as e:
            print(f"Could not load Rose image: {e}")
            return None

    def generate_meme_from_prompt(self, user_prompt, category="general"):
        """
        Generate a completely fresh meme from a user prompt
        Uses Claude to create unique, contextual meme text
        
        Args:
            user_prompt: What the user wants the meme to be about
            category: Type of meme (moderation, token, community, cheeky)
            
        Returns:
            BytesIO object containing the meme image
        """
        try:
            print(f"🎨 Generating fresh meme from: {user_prompt}")
            
            # Step 1: Use Claude to generate meme text based on prompt
            meme_text = self._generate_meme_text_with_claude(user_prompt, category)
            print(f"✨ Generated caption: {meme_text}")
            
            # Step 2: Create the meme image with the generated text + Rose reference
            meme_image = self._create_meme_image(meme_text)
            
            return meme_image
            
        except Exception as e:
            print(f"Error generating meme: {e}")
            return self._create_fallback_meme(user_prompt)

    def _generate_meme_text_with_claude(self, user_prompt, category):
        """
        Use Claude API to generate unique, contextual meme text
        
        Args:
            user_prompt: What the user wants the meme about
            category: Meme category/vibe
            
        Returns:
            String with the generated meme caption
        """
        
        # Category-specific tone instructions
        tone_instructions = {
            "moderation": "Rose bot moderating chat, tough love vibe",
            "token": "$ROSE token trading, bullish/bearish energy, market humor",
            "community": "Community building, group vibes, togetherness",
            "cheeky": "Confident, sassy, flirty Rose energy with humor",
            "general": "Fun, witty, meme-worthy caption"
        }
        
        tone = tone_instructions.get(category, tone_instructions["general"])
        
        prompt = f"""You are a meme caption generator. Create a short, punchy meme caption inspired by Rose bot.

Rose's character: {self.rose_character_prompt}

User's prompt: {user_prompt}
Meme vibe/category: {tone}

Create a single, creative meme caption that:
1. Is funny and shareable
2. Captures the Rose energy/personality
3. Relates to the user's prompt
4. Is SHORT (max 200 characters, ideally 50-150 chars)
5. Works for a meme format
6. Can include line breaks for multi-line memes

Return ONLY the caption text, nothing else. No quotes, no explanation.
If multi-line, use \\n for line breaks.

Examples of good outputs:
"Rose: *exists*\\nChat: *goes wild*"
"Me: tries to bypass Rose\\nRose: That's illegal"
"POV: You're a spammer and Rose just looked at you"
"""

        message = self.client.messages.create(
            model="claude-opus-4-20250514",
            max_tokens=300,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        caption = message.content[0].text.strip()
        # Handle escaped newlines
        caption = caption.replace('\\n', '\n')
        return caption

    def _create_meme_image(self, meme_text, width=900, height=600):
        """
        Create a meme image with generated text + Rose avatar
        
        Args:
            meme_text: The caption to display
            width: Image width
            height: Image height
            
        Returns:
            BytesIO with PNG meme image
        """
        
        # Rose-themed colors
        bg_colors = [
            (26, 26, 46),    # Dark blue
            (45, 45, 100),   # Purple-blue
            (70, 30, 70),    # Dark rose
            (40, 20, 60),    # Deep rose
        ]
        
        # Create base image with Rose theme colors
        bg_color = bg_colors[hash(meme_text) % len(bg_colors)]
        img = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(img)
        
        # Add Rose avatar if available
        if self.rose_image:
            rose_copy = self.rose_image.copy()
            rose_copy.thumbnail((250, 250), Image.Resampling.LANCZOS)
            # Place Rose in bottom right
            img.paste(rose_copy, (width - 280, height - 280), rose_copy)
        
        # Try to load a nice font
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48
            )
            small_font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32
            )
        except:
            font = ImageFont.load_default()
            small_font = font
        
        # Wrap text to fit
        wrapper = textwrap.TextWrapper(width=25)
        wrapped_text = '\n'.join(wrapper.wrap(text=meme_text))
        
        # Calculate text position (left side, centered vertically)
        bbox = draw.textbbox((0, 0), wrapped_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = 40
        y = (height - text_height) // 2
        
        # Draw text outline (black border)
        outline_color = (0, 0, 0)
        text_color = (255, 200, 220)  # Light rose color
        
        for adj_x in range(-3, 4):
            for adj_y in range(-3, 4):
                if adj_x != 0 or adj_y != 0:
                    draw.text(
                        (x + adj_x, y + adj_y), 
                        wrapped_text, 
                        font=font, 
                        fill=outline_color
                    )
        
        # Draw main text
        draw.text((x, y), wrapped_text, font=font, fill=text_color)
        
        # Add Rose branding
        try:
            rose_text = "✨ Rose Meme ✨"
            draw.text((40, height - 60), rose_text, font=small_font, fill=(255, 100, 150))
        except:
            pass
        
        # Save to bytes
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        return img_bytes

    def _create_fallback_meme(self, text):
        """Create a simple fallback meme if generation fails"""
        img = Image.new('RGB', (600, 400), (26, 26, 46))
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32
            )
        except:
            font = ImageFont.load_default()
        
        wrapper = textwrap.TextWrapper(width=20)
        wrapped = '\n'.join(wrapper.wrap(text=text))
        
        draw.text((50, 100), wrapped, font=font, fill=(255, 200, 220))
        draw.text((50, 350), "🌹 Rose Meme 🌹", font=font, fill=(255, 100, 150))
        
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        return img_bytes
