"""
Dynamic Image Generator - Creates unique Rose images using Claude + gpt-image-1
Claude generates detailed descriptions, gpt-image-1 edits rose_avatar_alt.png as base.
Text is added dynamically by gpt-image-1 during creation - not post-processed.
Target size: 852x1280 (portrait orientation)
"""

import anthropic
import openai
import base64
import random
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import textwrap
import os

# Always use rose_avatar_alt.png as the base reference
ROSE_BASE_IMAGE = "rose_avatar_alt.png"


def detect_media_type(data: bytes) -> str:
    """Detect image media type from magic bytes."""
    if data[:3] == b'\xff\xd8\xff':
        return "image/jpeg"
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return "image/gif"
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return "image/webp"
    return "image/jpeg"


class RoseImageGenerator:
    """Generate unique Rose meme images using Claude + gpt-image-1."""

    def __init__(self):
        """Initialize with Claude and OpenAI clients."""
        self.claude_client = anthropic.Anthropic()
        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.rose_base = self._load_rose_base()
        
        # Target dimensions (portrait)
        self.target_width = 852
        self.target_height = 1280

    def _load_rose_base(self):
        """Load rose_avatar_alt.png as the base reference."""
        try:
            with open(ROSE_BASE_IMAGE, "rb") as f:
                raw = f.read()
            media_type = detect_media_type(raw)
            b64_data = base64.standard_b64encode(raw).decode("utf-8")
            print(f"✅ Loaded {ROSE_BASE_IMAGE} as {media_type}")
            return {
                "filename": ROSE_BASE_IMAGE,
                "media_type": media_type,
                "b64_data": b64_data,
                "raw": raw,
            }
        except Exception as e:
            print(f"❌ Error loading {ROSE_BASE_IMAGE}: {e}")
            return None

    def generate_rose_image(self, meme_prompt, meme_caption):
        """
        Generate a unique Rose image based on the meme prompt.
        
        Flow:
        1. Claude analyzes Rose base image and writes a visual description
        2. gpt-image-1 edit mode uses rose_avatar_alt.png as base
        3. gpt-image-1 transforms it AND adds caption text dynamically
        4. Return the edited image with caption already integrated
        """
        try:
            # Step 1: Generate visual description from Claude
            visual_description = self._generate_rose_description(meme_prompt, meme_caption)
            print(f"✅ Description: {visual_description}")
            
            # Step 2: Generate image using gpt-image-1 edit mode
            # Caption is added by gpt-image-1 during the edit process
            rose_image = self._generate_image_edit(visual_description, meme_caption)
            print(f"✅ Image generated successfully")
            
            return rose_image
            
        except Exception as e:
            print(f"❌ Error generating Rose image: {e}")
            return self._create_fallback_image(meme_caption)

    def _generate_rose_description(self, meme_prompt, meme_caption):
        """Use Claude to generate detailed Rose visual description."""
        
        if not self.rose_base:
            print("⚠️ No base image loaded, using generic description")
            return "Rose stands confidently with orange/red wavy hair and a green bow, wearing a vintage outfit in a retro pinup style."
        
        # Build content with Rose base image
        content = [
            {
                "type": "text",
                "text": "Study this reference image of Rose to understand her core appearance and characteristics:"
            },
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": self.rose_base["media_type"],
                    "data": self.rose_base["b64_data"],
                }
            },
            {
                "type": "text",
                "text": f"""Based on this reference image of Rose, write a detailed visual description for image editing.

Meme context: "{meme_prompt}"
Caption: "{meme_caption}"

REQUIREMENTS:
- ALWAYS keep: Rose's core face structure, orange/red wavy hair, green bow, skin tone, retro 1950s pinup art style
- CAN CHANGE: outfit, pose, facial expressions, hairstyling details, props, accessories, background, setting
- Be VERY specific about: new outfit details, pose/stance, props, background, lighting, mood
- Include guidance on WHERE caption text should be placed (top, side, middle, overlay) and what font style would fit best
- Return ONLY the description (2-3 sentences, no preamble)

Example: "Rose wears a sleek business suit with a laptop, sitting confidently at a modern desk with the green bow still in her styled hair. She has a focused, determined expression. Place caption in elegant serif font at the top-left corner of the image, overlaid semi-transparently."""
        }}
        
        try:
            message = self.claude_client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=250,
                messages=[{"role": "user", "content": content}]
            )
            
            description = message.content[0].text.strip()
            return description
            
        except Exception as e:
            print(f"⚠️ Error generating description: {e}")
            return "Rose stands confidently in a retro vintage style with her orange hair and green bow, looking fabulous."

    def _generate_image_edit(self, rose_description, caption):
        """
        Use gpt-image-1 edit mode with rose_avatar_alt.png as the base.
        The prompt tells gpt-image-1 to add the caption text dynamically during creation.
        """
        
        if not self.rose_base:
            print("⚠️ No base image available")
            return self._create_fallback_image(caption)
        
        print(f"📸 Using {self.rose_base['filename']} as base image")
        
        # Convert to RGBA PNG in memory (required by gpt-image-1 edit)
        try:
            img = Image.open(BytesIO(self.rose_base["raw"])).convert("RGBA")
            png_bytes = BytesIO()
            img.save(png_bytes, format="PNG")
            png_bytes.seek(0)
            png_bytes.name = "rose.png"
        except Exception as e:
            print(f"❌ Error preparing base image: {e}")
            return self._create_fallback_image(caption)
        
        # Build the edit prompt - tell gpt-image-1 to ADD the caption text
        prompt = (
            "This is Rose. Preserve her EXACT core characteristics: "
            "face structure, eye shape, orange/red wavy hair, green bow, skin tone, and retro 1950s pinup art style. "
            "She must remain recognizable as the same character. "
            "Only change her outfit, pose, facial expression, hairstyling, props, and background to match: "
            f"{rose_description} "
            "\n\nIMPORTANT: Add the caption text dynamically to the image during creation. "
            f"Caption: '{caption}' "
            "Place the text in a natural location that doesn't cover important features - "
            "use creative positioning (top, side, corner, overlay) and choose an appropriate font style. "
            "The text should look natural and integrated into the overall composition. "
            "You can use different font styles, sizes, and colors as appropriate to the meme. "
            "Maintain the retro 1950s pinup illustration style throughout."
        )
        
        # Truncate if too long
        if len(prompt) > 1500:
            prompt = prompt[:1500]
        
        try:
            print(f"🎨 Calling gpt-image-1 edit mode with caption integration...")
            response = self.openai_client.images.edit(
                model="gpt-image-1",
                image=png_bytes,
                prompt=prompt,
                size="1024x1024",
                n=1,
            )
            
            # Extract image data and convert to PIL Image
            image_data = base64.b64decode(response.data[0].b64_json)
            return Image.open(BytesIO(image_data))
            
        except Exception as e:
            print(f"❌ Error editing image with gpt-image-1: {e}")
            return self._create_fallback_image(caption)

    def compose_meme(self, rose_image, caption):
        """
        Compose final meme - Rose image already has caption integrated by gpt-image-1.
        Just resize to target dimensions.
        """
        
        try:
            # Resize to target dimensions
            rose_image = rose_image.resize(
                (self.target_width, self.target_height),
                Image.Resampling.LANCZOS
            )
            meme = rose_image.convert('RGB')
            
            # Save to bytes
            img_bytes = BytesIO()
            meme.save(img_bytes, format='JPEG', quality=90)
            img_bytes.seek(0)
            
            return img_bytes
            
        except Exception as e:
            print(f"❌ Error composing meme: {e}")
            return self._create_fallback_image(caption)

    def _create_fallback_image(self, caption):
        """Create a simple fallback image if generation fails."""
        img = Image.new('RGB', (self.target_width, self.target_height), (26, 26, 46))
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                32
            )
        except Exception:
            font = ImageFont.load_default()
        
        text = "Rose Meme\n(Image generation unavailable)"
        draw.text((50, 600), text, font=font, fill=(255, 200, 220))
        
        # Add caption if provided
        if caption:
            try:
                small_font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    24
                )
            except Exception:
                small_font = ImageFont.load_default()
            
            draw.text((50, 700), caption, font=small_font, fill=(255, 255, 255))
        
        img_bytes = BytesIO()
        img.save(img_bytes, format='JPEG', quality=90)
        img_bytes.seek(0)
        
        return img_bytes
