"""
Dynamic Image Generator - Creates unique Rose images using Claude + gpt-image-1
Claude sees all Rose reference images and generates a description.
gpt-image-1 edit mode uses a real Rose image as the base, ensuring character consistency.
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

ROSE_REFERENCE_FILES = [
    "rose_avatar.png",
    "rose_avatar_alt.png",
    "rose_avatar_alt2.jpg",
    "rose_avatar_alt3.jpg",
    "rose_avatar_alt4.jpg",
]


def detect_media_type(data: bytes) -> str:
    """Detect image media type from magic bytes instead of trusting file extension."""
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
        self.rose_references = self._load_rose_references()
        
        # Target dimensions (portrait)
        self.target_width = 852
        self.target_height = 1280

    def _load_rose_references(self):
        """Load Rose reference images, detecting actual media type from file bytes."""
        references = []
        for filename in ROSE_REFERENCE_FILES:
            try:
                with open(filename, "rb") as f:
                    raw = f.read()
                media_type = detect_media_type(raw)
                b64_data = base64.standard_b64encode(raw).decode("utf-8")
                references.append({
                    "filename": filename,
                    "media_type": media_type,
                    "b64_data": b64_data,
                    "raw": raw,
                })
                print(f"✅ Loaded {filename} as {media_type}")
            except Exception as e:
                print(f"⚠️ Could not load {filename}: {e}")
        
        if not references:
            print("⚠️ No Rose reference images loaded!")
        
        return references

    def generate_rose_image(self, meme_prompt, meme_caption):
        """
        Generate a unique Rose image based on the meme prompt.
        
        Flow:
        1. Claude analyzes Rose reference images and writes a visual description
        2. gpt-image-1 edit mode uses a random Rose image as base
        3. gpt-image-1 transforms it according to the description
        4. Return the edited image
        """
        try:
            # Step 1: Generate visual description from Claude
            visual_description = self._generate_rose_description(meme_prompt, meme_caption)
            print(f"✅ Description: {visual_description}")
            
            # Step 2: Generate image using gpt-image-1 edit mode
            rose_image = self._generate_image_edit(visual_description)
            print(f"✅ Image generated successfully")
            
            return rose_image
            
        except Exception as e:
            print(f"❌ Error generating Rose image: {e}")
            return self._create_fallback_image()

    def _generate_rose_description(self, meme_prompt, meme_caption):
        """Use Claude to generate detailed Rose visual description."""
        
        if not self.rose_references:
            print("⚠️ No reference images, using generic description")
            return "Rose stands confidently with orange wavy hair and a green bow, wearing a vintage outfit in a retro pinup style."
        
        # Build content with Rose reference images
        content = [
            {
                "type": "text",
                "text": "Study these reference images of Rose to understand her appearance and style:"
            }
        ]
        
        # Add all Rose reference images
        for ref in self.rose_references:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": ref["media_type"],
                    "data": ref["b64_data"],
                }
            })
        
        # Add the prompt
        content.append({
            "type": "text",
            "text": f"""Based on these reference images of Rose, write a 1-2 sentence visual description for image editing.

Meme context: "{meme_prompt}"

REQUIREMENTS:
- ALWAYS keep: orange/red wavy hair, green hair accessory, confident expression, retro 1950s pinup style
- CHANGE: outfit, pose, props, background to match the meme context
- Be specific about clothing, pose, props, and setting
- Leave the BOTTOM 20% clear for caption text
- Return ONLY the description (1-2 sentences, no preamble)

Example: "Rose wears a business suit and confidently stands at a desk with charts, orange/red hair neat with green bow, serious focused expression, office setting with clear space at bottom."""
        })
        
        try:
            message = self.claude_client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=150,
                messages=[{"role": "user", "content": content}]
            )
            
            description = message.content[0].text.strip()
            return description
            
        except Exception as e:
            print(f"⚠️ Error generating description: {e}")
            return "Rose stands confidently with orange wavy hair and a green bow, wearing a vintage outfit in a retro pinup style."

    def _generate_image_edit(self, rose_description):
        """
        Use gpt-image-1 edit mode with a real Rose image as the base.
        This preserves Rose's character while editing the scene.
        """
        
        if not self.rose_references:
            print("⚠️ No reference images for editing")
            return self._create_fallback_image()
        
        # Select a random Rose reference image as the base
        base_ref = random.choice(self.rose_references)
        print(f"📸 Using {base_ref['filename']} as base image")
        
        # Convert to RGBA PNG in memory (required by gpt-image-1 edit)
        try:
            img = Image.open(BytesIO(base_ref["raw"])).convert("RGBA")
            png_bytes = BytesIO()
            img.save(png_bytes, format="PNG")
            png_bytes.seek(0)
            png_bytes.name = "rose.png"
        except Exception as e:
            print(f"❌ Error preparing base image: {e}")
            return self._create_fallback_image()
        
        # Build the edit prompt
        prompt = (
            "This is Rose. Preserve her EXACT face, facial features, eye color, "
            "red/orange wavy hair, green bow, skin tone, and art style with no changes whatsoever. "
            "She must look identical to the reference. "
            "Only change her outfit, pose, props, and background to match this scene: "
            f"{rose_description} "
            "Keep the bottom quarter of the image simple and uncluttered for caption text. "
            "Maintain the retro 1950s pinup illustration style throughout."
        )
        
        # Truncate if too long
        if len(prompt) > 1000:
            prompt = prompt[:1000]
        
        try:
            print(f"🎨 Calling gpt-image-1 edit mode...")
            response = self.openai_client.images.edit(
                model="gpt-image-1",
                image=png_bytes,
                prompt=prompt,
                size="1024x1536",
                n=1,
            )
            
            # Extract image data and convert to PIL Image
            image_data = base64.b64decode(response.data[0].b64_json)
            return Image.open(BytesIO(image_data))
            
        except Exception as e:
            print(f"❌ Error editing image with gpt-image-1: {e}")
            return self._create_fallback_image()

    def compose_meme(self, rose_image, caption):
        """
        Compose final meme with Rose image + caption text.
        - Resizes to 852x1280 (portrait)
        - Places caption at bottom with dark band
        - Font size adapts to caption length
        - Uses efficient paste() for dark band
        """
        
        try:
            # Resize to target dimensions
            rose_image = rose_image.resize(
                (self.target_width, self.target_height),
                Image.Resampling.LANCZOS
            )
            meme = rose_image.convert('RGB')
            
            # Adapt font size based on caption length
            if len(caption) < 60:
                font_size = 48
                wrap_width = 20
            elif len(caption) < 100:
                font_size = 40
                wrap_width = 24
            else:
                font_size = 32
                wrap_width = 30
            
            # Load font
            try:
                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    font_size
                )
            except Exception:
                font = ImageFont.load_default()
            
            # Wrap text
            wrapper = textwrap.TextWrapper(width=wrap_width)
            wrapped = '\n'.join(wrapper.wrap(text=caption))
            
            # Measure text
            tmp_draw = ImageDraw.Draw(meme)
            bbox = tmp_draw.textbbox((0, 0), wrapped, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            
            # Calculate band position and height
            padding = 20
            band_height = text_h + padding * 2
            band_top = self.target_height - band_height
            
            # Draw dark band at bottom using paste (fast)
            dark_band = Image.new('RGB', (self.target_width, band_height), (0, 0, 0))
            meme.paste(dark_band, (0, band_top))
            
            # Add fade gradient effect
            fade_height = 30
            if band_top - fade_height > 0:
                fade_band = Image.new('RGB', (self.target_width, fade_height), (0, 0, 0))
                existing = meme.crop((0, band_top - fade_height, self.target_width, band_top))
                blended = Image.blend(existing, fade_band, alpha=0.3)
                meme.paste(blended, (0, band_top - fade_height))
            
            # Draw text
            draw = ImageDraw.Draw(meme)
            
            # Center text horizontally, position in band
            x = (self.target_width - text_w) // 2
            y = band_top + padding
            
            # Draw text outline for crispness
            for adj_x in [-2, -1, 0, 1, 2]:
                for adj_y in [-2, -1, 0, 1, 2]:
                    if adj_x != 0 or adj_y != 0:
                        draw.text((x + adj_x, y + adj_y), wrapped, font=font, fill=(0, 0, 0))
            
            # Draw main text (white)
            draw.text((x, y), wrapped, font=font, fill=(255, 255, 255))
            
            # Save to bytes
            img_bytes = BytesIO()
            meme.save(img_bytes, format='JPEG', quality=90)
            img_bytes.seek(0)
            
            return img_bytes
            
        except Exception as e:
            print(f"❌ Error composing meme: {e}")
            return self._create_fallback_meme(caption)

    def _create_fallback_image(self):
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
        
        img_bytes = BytesIO()
        img.save(img_bytes, format='JPEG', quality=90)
        img_bytes.seek(0)
        
        return img_bytes

    def _create_fallback_meme(self, caption):
        """Create fallback meme with caption if image generation fails."""
        img = Image.new('RGB', (self.target_width, self.target_height), (26, 26, 46))
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                32
            )
        except Exception:
            font = ImageFont.load_default()
        
        # Draw fallback text
        text = "Rose Meme\n(Image generation unavailable)"
        draw.text((50, 600), text, font=font, fill=(255, 200, 220))
        
        # Add caption band
        band_height = 200
        band_top = self.target_height - band_height
        dark_band = Image.new('RGB', (self.target_width, band_height), (0, 0, 0))
        img.paste(dark_band, (0, band_top))
        
        # Draw caption
        wrapper = textwrap.TextWrapper(width=25)
        wrapped = '\n'.join(wrapper.wrap(text=caption))
        draw.text((40, band_top + 20), wrapped, font=font, fill=(255, 255, 255))
        
        img_bytes = BytesIO()
        img.save(img_bytes, format='JPEG', quality=90)
        img_bytes.seek(0)
        
        return img_bytes
