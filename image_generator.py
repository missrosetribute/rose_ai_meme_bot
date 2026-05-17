"""
Dynamic Image Generator - Creates unique Rose images using Claude + DALL-E 3
Claude generates descriptions, DALL-E 3 creates the images
"""

import anthropic
import openai
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import base64
import textwrap
import os

# Map filenames to their correct media types
ROSE_REFERENCES = [
    ("rose_avatar.png", "image/png"),
    ("rose_avatar_alt.png", "image/png"),
    ("rose_avatar_alt2.png", "image/png"),
    ("rose_avatar_alt3.jpg", "image/jpeg"),  # Fixed: was .png
    ("rose_avatar_alt4.jpg", "image/jpeg"),  # Fixed: was .png
]


class RoseImageGenerator:

    def __init__(self):
        """Initialize with Claude for descriptions and OpenAI for image generation"""
        self.claude_client = anthropic.Anthropic()
        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.rose_references = self._load_rose_references()

    def _load_rose_references(self):
        """Load Rose reference images for Claude to understand her appearance"""
        references = []
        for filename, media_type in ROSE_REFERENCES:
            try:
                with open(filename, "rb") as f:
                    data = base64.standard_b64encode(f.read()).decode("utf-8")
                    references.append((filename, media_type, data))
            except Exception as e:
                print(f"Could not load reference image {filename}: {e}")
        return references

    def generate_rose_image(self, meme_prompt, meme_caption):
        """
        Generate a unique Rose image based on the meme prompt
        Flow:
        1. Claude analyzes prompt + sees Rose references
        2. Claude creates detailed visual description
        3. DALL-E 3 generates image from description
        4. Return the image
        """
        visual_description = self._generate_rose_description(meme_prompt, meme_caption)
        rose_image = self._generate_image_dalle3(visual_description)
        return rose_image

    def _generate_rose_description(self, meme_prompt, meme_caption):
        """Use Claude to generate detailed Rose visual description"""

        content = [
            {
                "type": "text",
                "text": "Study these reference images of Rose to understand her appearance:"
            }
        ]

        # Add Rose reference images with correct media types
        for filename, media_type, base64_data in self.rose_references:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,  # Fixed: now uses correct type per file
                    "data": base64_data
                }
            })

        content.append({
            "type": "text",
            "text": f"""Based on these reference images of Rose, create a concise visual description for an image generation AI.

Meme context: "{meme_prompt}"
Meme caption: "{meme_caption}"

Generate a description that:
1. MAINTAINS Rose's core identity:
   - Orange/red wavy hair with green bow (required)
   - Confident, sassy expression (required)
   - Retro 1950s pinup aesthetic (required)

2. ADAPTS to the meme context:
   - Appropriate outfit/clothing
   - Relevant pose and body language
   - Fitting accessories/props
   - Suitable background/setting

IMPORTANT:
- Keep the description to 2 sentences maximum
- Focus on visual elements only (no drama, no relationships, no narrative)
- Describe what Rose looks like and where she is, nothing else
- Return ONLY the description, no preamble"""
        })

        try:
            message = self.claude_client.messages.create(
                model="claude-sonnet-4-5",  # Fixed: updated from deprecated claude-opus-4-20250514
                max_tokens=200,
                messages=[
                    {"role": "user", "content": content}
                ]
            )
            description = message.content[0].text.strip()
            return description
        except Exception as e:
            print(f"Error generating description: {e}")
            return "Rose stands confidently with orange wavy hair and a green bow, wearing a vintage outfit, retro pinup style."

    def _generate_image_dalle3(self, rose_description):
        """Generate image using DALL-E 3 from Rose description"""

        # Keep prompt short and visual-only to avoid content policy rejections.
        # DALL-E 3 is sensitive to long or narrative-heavy prompts.
        base = (
            "Cartoon illustration of a confident retro pinup woman with orange wavy hair "
            "and a green bow. "
        )
        style = " Vibrant meme-style art, bold outlines, colorful, high quality."

        # Truncate description if needed so total prompt stays well under 1000 chars
        max_desc_len = 900 - len(base) - len(style)
        safe_description = rose_description[:max_desc_len]

        prompt = base + safe_description + style

        try:
            response = self.openai_client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )

            image_url = response.data[0].url
            img_response = requests.get(image_url, timeout=30)

            if img_response.status_code == 200:
                return Image.open(BytesIO(img_response.content))
            else:
                print(f"Failed to download image: HTTP {img_response.status_code}")
                return self._create_fallback_image(rose_description)

        except Exception as e:
            print(f"Error generating image with DALL-E 3: {e}")
            return self._create_fallback_image(rose_description)

    def compose_meme(self, rose_image, caption):
        """Compose final meme with Rose image + caption text"""

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
        text_h = bbox[3] - bbox[1]
        text_w = bbox[2] - bbox[0]

        x = (900 - text_w) // 2
        y = (600 - text_h) // 2

        outline_color = (0, 0, 0)
        text_color = (255, 255, 255)

        for adj_x in range(-3, 4):
            for adj_y in range(-3, 4):
                if adj_x != 0 or adj_y != 0:
                    draw.text((x + adj_x, y + adj_y), wrapped, font=font, fill=outline_color)

        draw.text((x, y), wrapped, font=font, fill=text_color)

        img_bytes = BytesIO()
        meme.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes

    def _create_fallback_image(self, description):
        """Create fallback meme if image generation fails"""
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
