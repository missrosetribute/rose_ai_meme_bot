"""
Dynamic Image Generator - Original Rose Cartoon Style
Uses gpt-image-1 EDIT mode with og_rose_avatar_alt.png as base reference.
Matches the same pattern as image_generator.py (vintage style).
"""

import anthropic
import openai
import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import os

# Always use og_rose_avatar_alt.png as the base reference
ROSE_BASE_IMAGE = "og_rose_avatar_alt.png"


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


class OGRoseImageGenerator:
    """Generate original Rose meme images using Claude + gpt-image-1 edit mode."""

    def __init__(self):
        """Initialize with Claude and OpenAI clients."""
        self.claude_client = anthropic.Anthropic()
        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.rose_base = self._load_rose_base()

        # Target dimensions
        self.target_width = 1024
        self.target_height = 1024

    def _load_rose_base(self):
        """Load og_rose_avatar_alt.png as the base reference."""
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

    def generate_rose_image(self, meme_prompt: str, meme_caption: str) -> Image.Image:
        """Generate an OG Rose style meme."""
        try:
            visual_description = self._generate_rose_description(meme_prompt, meme_caption)
            print(f"✅ Description: {visual_description}")

            rose_image = self._generate_image_edit(visual_description, meme_caption)
            print("✅ OG Rose image generated")
            return rose_image

        except Exception as e:
            print(f"❌ Error generating OG Rose image: {e}")
            return self._create_fallback_image(meme_caption)

    def _generate_rose_description(self, meme_prompt: str, meme_caption: str) -> str:
        """Use Claude to generate detailed Rose visual description."""

        if not self.rose_base:
            print("⚠️ No base image loaded, using generic description")
            return "Rose stands confidently with her signature colorful style, looking fabulous."

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
- ALWAYS keep: Rose's core face structure, hair color and style, skin tone, and her original illustration art style
- CAN CHANGE: outfit, pose, facial expression, props, accessories, background, setting
- Be VERY specific about: new outfit details, pose/stance, props, background, lighting, mood
- Include guidance on WHERE caption text should be placed (top, side, middle, overlay) and what font style would fit best
- Return ONLY the description (2-3 sentences, no preamble)"""
            }
        ]

        try:
            message = self.claude_client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=250,
                messages=[{"role": "user", "content": content}]
            )
            return message.content[0].text.strip()
        except Exception as e:
            print(f"⚠️ Claude error: {e}")
            return "Rose stands confidently in her signature style, looking fabulous."

    def _generate_image_edit(self, rose_description: str, caption: str) -> Image.Image:
        """Use gpt-image-1 edit mode with og_rose_avatar_alt.png as the base."""

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

        prompt = (
            "CHARACTER CONSISTENCY IS CRITICAL. "
            "The reference image shows Rose - replicate her EXACTLY: same face, same hair color and style, "
            "same eye color, same skin tone, same original illustration art style. "
            "She must remain recognizable as the same character. "
            "Only change her outfit, pose, facial expression, props, and background to match: "
            f"Only change the scene: {rose_description} "
            "\n\nIMPORTANT: Add the caption text dynamically to the image during creation. "
            f"Caption context: {caption}"
            "Place the text in a natural location that doesn't cover important features. "
            "The text should look natural and integrated into the overall composition."
        )
    

        if len(prompt) > 1500:
            prompt = prompt[:1500]

        try:
            print("🎨 Calling gpt-image-1 edit mode...")
            response = self.openai_client.images.edit(
                model="gpt-image-1",
                image=png_bytes,
                prompt=prompt,
                size="1024x1024",
                n=1,
            )

            image_data = base64.b64decode(response.data[0].b64_json)
            return Image.open(BytesIO(image_data))

        except Exception as e:
            print(f"❌ Error editing image with gpt-image-1: {e}")
            return self._create_fallback_image(caption)

    def compose_meme(self, rose_image: Image.Image, caption: str):
        """Resize to target dimensions."""
        try:
            rose_image = rose_image.resize(
                (self.target_width, self.target_height),
                Image.Resampling.LANCZOS
            )
            meme = rose_image.convert("RGB")
            img_bytes = BytesIO()
            meme.save(img_bytes, format="JPEG", quality=90)
            img_bytes.seek(0)
            return img_bytes
        except Exception as e:
            print(f"❌ Compose error: {e}")
            return self._create_fallback_image(caption)

    def _create_fallback_image(self, caption: str):
        """Create a simple fallback image if generation fails."""
        img = Image.new("RGB", (self.target_width, self.target_height), (26, 26, 46))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
        except Exception:
            font = ImageFont.load_default()
        draw.text((50, 600), "OG Rose Meme", font=font, fill=(255, 200, 220))
        if caption:
            try:
                small_font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24
                )
            except Exception:
                small_font = ImageFont.load_default()
            draw.text((50, 700), caption, font=small_font, fill=(255, 255, 255))
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG", quality=90)
        img_bytes.seek(0)
        return img_bytes
