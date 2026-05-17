"""
Dynamic Image Generator - Creates unique Rose images using Claude + gpt-image-1
Claude generates descriptions, gpt-image-1 creates the images
"""

import anthropic
import openai
import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import textwrap
import os

ROSE_REFERENCE_FILES = [
    "rose_avatar.png",
    "rose_avatar_alt.png",
    "rose_avatar_alt2.png",
    "rose_avatar_alt3.jpg",
    "rose_avatar_alt4.jpg",
]


def detect_media_type(data: bytes) -> str:
    """Detect image media type from magic bytes instead of trusting the file extension."""
    if data[:3] == b'\xff\xd8\xff':
        return "image/jpeg"
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return "image/gif"
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return "image/webp"
    return "image/jpeg"  # safe fallback


class RoseImageGenerator:

    def __init__(self):
        """Initialize with Claude for descriptions and OpenAI for image generation"""
        self.claude_client = anthropic.Anthropic()
        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.rose_references = self._load_rose_references()

    def _load_rose_references(self):
        """Load Rose reference images, detecting actual media type from file bytes."""
        references = []
        for filename in ROSE_REFERENCE_FILES:
            try:
                with open(filename, "rb") as f:
                    raw = f.read()
                media_type = detect_media_type(raw)
                data = base64.standard_b64encode(raw).decode("utf-8")
                references.append((filename, media_type, data))
                print(f"Loaded {filename} as {media_type}")
            except Exception as e:
                print(f"Could not load reference image {filename}: {e}")
        return references

    def generate_rose_image(self, meme_prompt, meme_caption):
        """
        Generate a unique Rose image based on the meme prompt.
        Flow:
          1. Claude analyzes prompt + sees Rose references
          2. Claude creates short visual description
          3. gpt-image-1 generates image from description
          4. Return the image
        """
        visual_description = self._generate_rose_description(meme_prompt, meme_caption)
        rose_image = self._generate_image(visual_description)
        return rose_image

    def _generate_rose_description(self, meme_prompt, meme_caption):
        """Use Claude to generate a short Rose visual description."""

        content = [
            {
                "type": "text",
                "text": "Study these reference images of Rose to understand her appearance:"
            }
        ]

        for filename, media_type, base64_data in self.rose_references:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,  # Detected from actual bytes, not filename
                    "data": base64_data
                }
            })

        content.append({
            "type": "text",
            "text": f"""Based on these reference images of Rose, write a 1-2 sentence visual description for an image generator.

Meme context: "{meme_prompt}"

Requirements:
- Orange/red wavy hair with green bow (always keep)
- Confident expression, retro 1950s pinup style (always keep)
- Adapt outfit, pose, props, and setting to match the meme context
- Describe ONLY what is visually depicted — no story, no relationships, no emotions
- Return ONLY the description, nothing else"""
        })

        try:
            message = self.claude_client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=150,
                messages=[{"role": "user", "content": content}]
            )
            description = message.content[0].text.strip()
            print(f"Generated description: {description}")
            return description
        except Exception as e:
            print(f"Error generating description: {e}")
            return "Rose stands confidently with orange wavy hair and a green bow, wearing a vintage outfit in a retro pinup style."

    def _generate_image(self, rose_description):
        """Generate image using gpt-image-1 from Rose description."""

        base = (
            "Cartoon illustration of a confident retro pinup woman with orange wavy hair "
            "and a green bow. "
        )
        style = " Vibrant meme-style art, bold outlines, colorful."

        max_desc_len = 900 - len(base) - len(style)
        safe_description = rose_description[:max_desc_len]
        prompt = base + safe_description + style

        try:
            response = self.openai_client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                size="1024x1024",
                n=1
            )

            # gpt-image-1 returns base64, not a URL
            image_data = base64.b64decode(response.data[0].b64_json)
            return Image.open(BytesIO(image_data))

        except Exception as e:
            print(f"Error generating image with gpt-image-1: {e}")
            return self._create_fallback_image(rose_description)

    def compose_meme(self, rose_image, caption):
        """Compose final meme with Rose image + caption text."""

        if rose_image.size != (900, 600):
            rose_image = rose_image.resize((900, 600), Image.Resampling.LANCZOS)

        meme = rose_image.convert('RGB')
        draw = ImageDraw.Draw(meme)

        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48
            )
        except Exception:
            font = ImageFont.load_default()

        wrapper = textwrap.TextWrapper(width=20)
        wrapped = '\n'.join(wrapper.wrap(text=caption))

        bbox = draw.textbbox((0, 0), wrapped, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        x = (900 - text_w) // 2
        y = (600 - text_h) // 2

        for adj_x in range(-3, 4):
            for adj_y in range(-3, 4):
                if adj_x != 0 or adj_y != 0:
                    draw.text((x + adj_x, y + adj_y), wrapped, font=font, fill=(0, 0, 0))

        draw.text((x, y), wrapped, font=font, fill=(255, 255, 255))

        img_bytes = BytesIO()
        meme.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes

    def _create_fallback_image(self, description):
        """Create a simple fallback image if generation fails."""
        img = Image.new('RGB', (900, 600), (26, 26, 46))
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32
            )
        except Exception:
            font = ImageFont.load_default()

        text = "Rose Meme\n(Image generation unavailable)"
        draw.text((50, 250), text, font=font, fill=(255, 200, 220))

        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes
