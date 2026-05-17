"""
Dynamic Image Generator - Creates unique Rose images using Claude + gpt-image-1
Claude sees all Rose reference images and generates a description.
gpt-image-1 edit mode uses a real Rose image as the base, ensuring character consistency.
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
                b64_data = base64.standard_b64encode(raw).decode("utf-8")
                references.append({
                    "filename": filename,
                    "media_type": media_type,
                    "b64_data": b64_data,
                    "raw": raw,
                })
                print(f"Loaded {filename} as {media_type}")
            except Exception as e:
                print(f"Could not load reference image {filename}: {e}")
        return references

    def generate_rose_image(self, meme_prompt, meme_caption):
        """
        Generate a unique Rose image based on the meme prompt.
        Flow:
          1. Claude sees all Rose reference images and writes a visual description
          2. gpt-image-1 edit mode takes a random Rose reference as the base image
             and transforms it according to the description — preserving her character
          3. Return the image
        """
        visual_description = self._generate_rose_description(meme_prompt, meme_caption)
        rose_image = self._generate_image_edit(visual_description)
        return rose_image

    def _generate_rose_description(self, meme_prompt, meme_caption):
        """Use Claude (with all Rose reference images) to generate a visual description."""

        content = [
            {
                "type": "text",
                "text": "Study these reference images of Rose to understand her appearance:"
            }
        ]

        for ref in self.rose_references:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": ref["media_type"],
                    "data": ref["b64_data"],
                }
            })

        content.append({
            "type": "text",
            "text": f"""Based on these reference images of Rose, write a 1-2 sentence visual description for an image editor.

Meme context: "{meme_prompt}"

Requirements:
- Keep her orange/red wavy hair and green bow (always)
- Keep her confident expression and retro 1950s pinup style (always)
- Describe the outfit, pose, props, and setting appropriate for the meme context
- Describe ONLY what is visually depicted — no story, no relationships, no emotions
- Leave the BOTTOM 20% of the image uncluttered — this is where the caption text will go
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
            return "Rose stands confidently with orange wavy hair and a green bow, wearing a vintage outfit in a retro pinup style, with clear space at the bottom of the image."

    def _generate_image_edit(self, rose_description):
        """
        Use gpt-image-1 edit mode with a real Rose image as the base.
        This anchors generation to the actual character rather than a text description alone.
        """

        if not self.rose_references:
            print("No reference images loaded, using fallback")
            return self._create_fallback_image(rose_description)

        base_ref = random.choice(self.rose_references)

        # Convert to RGBA PNG in memory — required by gpt-image-1 edit
        try:
            img = Image.open(BytesIO(base_ref["raw"])).convert("RGBA")
            png_bytes = BytesIO()
            img.save(png_bytes, format="PNG")
            png_bytes.seek(0)
            png_bytes.name = "rose.png"
        except Exception as e:
            print(f"Error preparing base image: {e}")
            return self._create_fallback_image(rose_description)

        prompt = (
            "This is Rose. Preserve her EXACT face, facial features, eye color, "
            "red/orange wavy hair, green bow, skin tone, and art style with no changes whatsoever. "
            "She must look identical to the reference. "
            "Only change her outfit, pose, props, and background to match this scene: "
            f"{rose_description} "
            "Keep the bottom quarter of the image simple and uncluttered for caption text. "
            "Maintain the retro 1950s pinup illustration style throughout."
        )

        if len(prompt) > 900:
            prompt = prompt[:900]

        try:
            response = self.openai_client.images.edit(
                model="gpt-image-1",
                image=png_bytes,
                prompt=prompt,
                size="852x1280",
                n=1,
            )

            # gpt-image-1 returns base64
            image_data = base64.b64decode(response.data[0].b64_json)
            return Image.open(BytesIO(image_data))

        except Exception as e:
            print(f"Error editing image with gpt-image-1: {e}")
            return self._create_fallback_image(rose_description)

    def compose_meme(self, rose_image, caption):
        """
        Compose final meme with Rose image + caption text.
        - Keeps the image size (852x1280) to avoid distortion
        - Rose's head must fit completely within the image frame
        - Places caption in the bottom area with a light grey gradient behind it
        - Font size adapts to caption length
        """

        # Keep square — do NOT reshape to 900x600, that causes distortion
        TARGET_SIZE = (852, 1280)
        rose_image = rose_image.resize(TARGET_SIZE, Image.Resampling.LANCZOS)
        meme = rose_image.convert('RGB')
        draw = ImageDraw.Draw(meme)

        # Adapt font size based on caption length
        if len(caption) < 60:
            font_size = 52
            wrap_width = 22
        elif len(caption) < 100:
            font_size = 44
            wrap_width = 26
        else:
            font_size = 36
            wrap_width = 32

        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size
            )
        except Exception:
            font = ImageFont.load_default()

        # Wrap caption text
        wrapper = textwrap.TextWrapper(width=wrap_width)
        wrapped = '\n'.join(wrapper.wrap(text=caption))

        # Measure text block
        bbox = draw.textbbox((0, 0), wrapped, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        padding = 24
        text_area_height = text_h + padding * 2

        # Position: horizontally centered, sitting above the bottom edge
        x = (TARGET_SIZE - text_w) // 2
        y = TARGET_SIZE - text_area_height - padding + padding  # near bottom

        # Draw a semi-transparent light grey gradient band behind the text for readability
        overlay = Image.new('RGBA', (TARGET_SIZE, TARGET_SIZE), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        band_top = y - padding
        overlay_draw.rectangle(
            [(0, band_top), (TARGET_SIZE, TARGET_SIZE)],
            fill=(0, 0, 0, 160)
        )
        meme = Image.alpha_composite(meme.convert('RGBA'), overlay).convert('RGB')
        draw = ImageDraw.Draw(meme)

        # Draw text with thin outline for extra crispness
        outline_color = (0, 0, 0)
        text_color = (255, 255, 255)

        for adj_x in [-2, -1, 0, 1, 2]:
            for adj_y in [-2, -1, 0, 1, 2]:
                if adj_x != 0 or adj_y != 0:
                    draw.text((x + adj_x, y + adj_y), wrapped, font=font, fill=outline_color)

        draw.text((x, y), wrapped, font=font, fill=text_color)

        img_bytes = BytesIO()
        meme.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes

    def _create_fallback_image(self, description):
        """Create a simple fallback image if generation fails."""
        img = Image.new('RGB', (1024, 1024), (26, 26, 46))
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32
            )
        except Exception:
            font = ImageFont.load_default()

        text = "Rose Meme\n(Image generation unavailable)"
        draw.text((50, 480), text, font=font, fill=(255, 200, 220))

        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes
