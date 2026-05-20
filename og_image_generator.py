"""
Dynamic Image Generator - Original Rose Cartoon Style
Uses pre-uploaded file_id from OpenAI Files API
Optimized for anime/cartoon illustration style
"""

import anthropic
import openai
import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import textwrap
import os

# Use your pre-uploaded file_id here
ROSE_BASE_FILE_ID = os.getenv('ROSE_OG_FILE_ID')  # file-xxxxx

# Reference file for Claude (local file)
ROSE_REFERENCE_FILES = [
    "og_rose_avatar_alt.jpg",
]


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
    """Generate original cartoon Rose meme images using pre-uploaded file_id."""

    def __init__(self):
        """Initialize with pre-uploaded file_id."""
        self.claude_client = anthropic.Anthropic()
        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        # Use pre-uploaded file_id
        self.rose_base_file_id = ROSE_BASE_FILE_ID
        if self.rose_base_file_id:
            print(f"✅ Using pre-uploaded OG Rose file_id: {self.rose_base_file_id}")
        else:
            print("⚠️ No file_id provided, will use base64 fallback")
        
        # Load reference for Claude
        self.rose_references_b64 = self._load_references_for_claude()
        
        # Target dimensions
        self.target_width = 1024
        self.target_height = 1024

    def _load_references_for_claude(self) -> list[dict]:
        """Load reference image as base64 for Claude."""
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
                })
                print(f"✅ Loaded OG Rose reference: {filename}")
            except Exception as e:
                print(f"⚠️ Could not load {filename}: {e}")
        return references

    def generate_rose_image(self, meme_prompt: str, meme_caption: str) -> Image.Image:
        """Generate an OG Rose style meme."""
        try:
            visual_description = self._generate_rose_description(meme_prompt, meme_caption)
            print(f"✅ Description: {visual_description}")
            
            rose_image = self._generate_image_edit(visual_description, meme_caption)
            print("✅ OG Rose image generated")
            return rose_image
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return self._create_fallback_image(meme_caption)

    def _generate_rose_description(self, meme_prompt: str, meme_caption: str) -> str:
        """Claude studies OG Rose and describes the scene with proper style guidance."""
        if not self.rose_references_b64:
            return "Rose, anime cartoon style with orange wavy hair and green bow, confident playful expression."

        content: list[dict] = [
            {"type": "text", "text": "Study this reference image of Rose carefully - this is the ORIGINAL cartoon illustration style:"}
        ]

        for ref in self.rose_references_b64:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": ref["media_type"],
                    "data": ref["b64_data"],
                },
            })

        content.append({
            "type": "text",
            "text": f"""You MUST preserve Rose's cartoon illustration style from the reference image. Create a scene description for this EXACT style.

**KEY CHARACTERISTICS TO PRESERVE:**
- Anime/cartoon illustration style (not photorealistic)
- Hand-drawn aesthetic with clean linework
- Orange/red wavy hair (stylized, not realistic)
- Green hair bow/accessory (always present)
- Confident, playful, flirty expression
- Smooth color palette with subtle shading
- Anime-style eyes and facial features
- Graceful, stylized body proportions

**Context:** {meme_prompt}
**Caption:** {meme_caption}

Create a NEW scene for Rose in this EXACT cartoon illustration style:
- Change outfit, setting, pose, props to fit the context
- Keep the illustration style consistent with the reference
- Describe the scene simply and clearly
- Suggest text placement if caption is needed

Return ONLY 2-3 sentences describing the new scene."""
        })

        try:
            message = self.claude_client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=300,
                messages=[{"role": "user", "content": content}],
            )
            return message.content[0].text.strip()
        except Exception as e:
            print(f"⚠️ Claude error: {e}")
            return "Rose in cartoon illustration style, confident and playful."

    def _generate_image_edit(self, rose_description: str, caption: str) -> Image.Image:
        """gpt-image-1 edit using file_id or base64 fallback."""
        # Emphasize the cartoon/illustration style in the prompt
        prompt = (
            "ORIGINAL CARTOON ROSE: This is a hand-drawn anime/cartoon illustration style. "
            "PRESERVE EXACTLY: Illustration style, orange wavy hair, green bow, confident playful expression, "
            "anime-style face and body, smooth color palette with subtle shading. "
            "CHANGE: outfit, pose, props, setting to match: "
            f"{rose_description} "
            "Maintain the exact cartoon/anime illustration style throughout. "
            "Do NOT make it photorealistic or 3D - keep it as a 2D illustration. "
            f"Add caption: '{caption}' in a style that fits the cartoon aesthetic. "
        )
        if len(prompt) > 1500:
            prompt = prompt[:1500]

        # Try file_id first (fast!)
        if self.rose_base_file_id:
            try:
                print(f"🎨 OG Rose gpt-image-1 edit via file_id")
                response = self.openai_client.images.edit(
                    model="gpt-image-1",
                    image=[{"type": "image_file", "file_id": self.rose_base_file_id}],
                    prompt=prompt,
                    size="1024x1024",
                    n=1,
                )
                image_data = base64.b64decode(response.data[0].b64_json)
                return Image.open(BytesIO(image_data))
            except Exception as e:
                print(f"⚠️ file_id failed: {e}, trying base64...")

        # Fallback to base64
        return self._generate_image_edit_base64(prompt)

    def _generate_image_edit_base64(self, prompt: str) -> Image.Image:
        """Fallback: send base64 inline."""
        try:
            with open("og_rose_avatar_alt.jpg", "rb") as f:
                raw = f.read()
            img = Image.open(BytesIO(raw)).convert("RGBA")
            png_bytes = BytesIO()
            img.save(png_bytes, format="PNG")
            png_bytes.seek(0)
            png_bytes.name = "rose.png"
            print("🎨 OG Rose gpt-image-1 edit via base64 (fallback)")
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
            print(f"❌ Base64 failed: {e}")
            return self._create_fallback_image("")

    def compose_meme(self, rose_image: Image.Image, caption: str):
        """Resize to target dimensions."""
        try:
            rose_image = rose_image.resize(
                (self.target_width, self.target_height),
                Image.Resampling.LANCZOS,
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
        """Fallback image."""
        img = Image.new("RGB", (self.target_width, self.target_height), (26, 26, 46))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
        except Exception:
            font = ImageFont.load_default()
        draw.text((50, 600), "OG Rose Meme", font=font, fill=(255, 200, 220))
        if caption:
            draw.text((50, 700), caption, font=font, fill=(255, 255, 255))
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG", quality=90)
        img_bytes.seek(0)
        return img_bytes
