"""
Dynamic Image Generator - Original Rose Cartoon Style
Uses gpt-image-1 EDIT mode with file_id reference for character consistency
Claude just describes the scene, gpt-image-1 uses the pre-loaded file_id to understand Rose
"""

import anthropic
import openai
import base64
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import os

# Use your pre-uploaded file_id here
ROSE_BASE_FILE_ID = os.getenv('ROSE_OG_FILE_ID')  # file-xxxxx


class OGRoseImageGenerator:
    """Generate original Rose meme images using gpt-image-1 edit mode with file_id reference."""

    def __init__(self):
        """Initialize with pre-uploaded file_id."""
        self.claude_client = anthropic.Anthropic()
        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.api_key = os.getenv('OPENAI_API_KEY')

        # Use pre-uploaded file_id
        self.rose_base_file_id = ROSE_BASE_FILE_ID
        if self.rose_base_file_id:
            print(f"✅ Using pre-uploaded OG Rose file_id: {self.rose_base_file_id}")
        else:
            print("⚠️ No file_id provided - gpt-image-1 won't have visual reference")

        # Target dimensions
        self.target_width = 1024
        self.target_height = 1024

    def generate_rose_image(self, meme_prompt: str, meme_caption: str) -> Image.Image:
        """Generate an OG Rose style meme."""
        try:
            scene_description = self._generate_scene_description(meme_prompt, meme_caption)
            print(f"✅ Scene description: {scene_description}")

            rose_image = self._generate_image(scene_description, meme_caption)
            print("✅ OG Rose image generated")
            return rose_image

        except Exception as e:
            print(f"❌ Error: {e}")
            return self._create_fallback_image(meme_caption)

    def _generate_scene_description(self, meme_prompt: str, meme_caption: str) -> str:
        """Claude describes the scene based on the prompt."""

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
        """Use gpt-image-1 EDIT mode with file_id reference."""

        prompt = (
            "CHARACTER CONSISTENCY IS CRITICAL. "
            "The reference image shows Rose - replicate her EXACTLY: same face, same hair color and style, "
            "same eye color, same skin tone, same vintage illustration art style. "
            "DO NOT alter her appearance in any way. "
            f"Only change the scene: {scene_description} "
            f"Caption context: {caption}"
        )

        try:
            # Download reference image using explicit auth header to avoid key issues
            file_response = requests.get(
                f"https://api.openai.com/v1/files/{self.rose_base_file_id}/content",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30
            )
            file_response.raise_for_status()
            ref_bytes = BytesIO(file_response.content)

            edit_response = self.openai_client.images.edit(
                model="gpt-image-1",
                image=ref_bytes,
                prompt=prompt,
                size="1024x1024",
                n=1,
                quality="high",
            )

            image_data = base64.b64decode(edit_response.data[0].b64_json)
            return Image.open(BytesIO(image_data))

        except Exception as e:
            print(f"❌ Generation failed: {e}")
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
