"""
Dynamic Image Generator - Original Rose Cartoon Style
Uses gpt-image-1 GENERATION mode with file_id reference for character consistency
Claude just describes the scene, gpt-image-1 uses the pre-loaded file_id to understand Rose
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
    """Generate original Rose meme images using gpt-image-1 generation mode with file_id reference."""

    def __init__(self):
        """Initialize with pre-uploaded file_id."""
        self.claude_client = anthropic.Anthropic()
        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        # Use pre-uploaded file_id
        self.rose_base_file_id = ROSE_BASE_FILE_ID
        if self.rose_base_file_id:
            print(f"✅ Using pre-uploaded OG Rose file_id: {self.rose_base_file_id}")
        else:
            print("⚠️ No file_id provided - gpt-image-1 won't have visual reference")
        
        # Target dimensions (portrait)
        self.target_width = 852
        self.target_height = 1280

    def generate_rose_image(self, meme_prompt: str, meme_caption: str) -> Image.Image:
        """Generate an OG Rose style meme."""
        try:
            # Claude just describes the scene based on the prompt
            scene_description = self._generate_scene_description(meme_prompt, meme_caption)
            print(f"✅ Scene description: {scene_description}")
            
            # gpt-image-1 uses file_id to see Rose and understands what to generate
            rose_image = self._generate_image(scene_description, meme_caption)
            print("✅ OG Rose image generated")
            return rose_image
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return self._create_fallback_image(meme_caption)

    def _generate_scene_description(self, meme_prompt: str, meme_caption: str) -> str:
        """Claude describes the scene based on the prompt (no image analysis needed)."""
        
        system_prompt = """You are a scene description writer for Rose meme generation.
        
Write a detailed description of a scene for Rose to be in, based on the given context.
Focus on: outfit, pose, props, setting, background, lighting, mood, actions.

Return ONLY the scene description (2-3 sentences). No preamble."""

        try:
            message = self.claude_client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=200,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": f"Create a scene for Rose: {meme_prompt}. Caption: {meme_caption}"
                    }
                ],
            )
            return message.content[0].text.strip()
        except Exception as e:
            print(f"⚠️ Claude error: {e}")
            return "Rose in a confident pose, looking fabulous."

    def _generate_image(self, scene_description: str, caption: str) -> Image.Image:
        """Use gpt-image-1 GENERATION mode with file_id reference."""
        
        # Build prompt that references the file_id
        # gpt-image-1 will use the file_id to understand Rose's appearance
        prompt = (
            "Generate a new illustration of Rose, matching the character shown in file_id. "
            f"Scene: {scene_description} "
            f"Caption: {caption} "
            "CRITICAL: Rose must look exactly like the reference character - "
            "same face, same hair, same features, same style. "
            "Only change the outfit, pose, setting, and props. "
            "Maintain the vintage pin-up illustration aesthetic throughout."
        )

        if len(prompt) > 3000:
            prompt = prompt[:3000]

        try:
            print(f"🎨 OG Rose gpt-image-1 GENERATION with file_id reference")
            
            # gpt-image-1 can now see the file_id and understand Rose's appearance
            response = self.openai_client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                size="1024x1536",
                n=1,
                quality="hd",
            )
            
            # Get the URL and download the image
            image_url = response.data[0].url
            image_data = self._download_image(image_url)
            return Image.open(BytesIO(image_data))
            
        except Exception as e:
            print(f"❌ Generation failed: {e}")
            return self._create_fallback_image("")

    def _download_image(self, url: str) -> bytes:
        """Download image from URL."""
        import requests
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.content

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
