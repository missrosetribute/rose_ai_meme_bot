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

class RoseImageGenerator:
    def __init__(self):
        """Initialize with Claude for descriptions and OpenAI for image generation"""
        self.claude_client = anthropic.Anthropic()
        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.rose_references = self._load_rose_references()
    
    def _load_rose_references(self):
        """Load Rose reference images for Claude to understand her appearance"""
        references = {}
        for filename in ["rose_avatar.png", "rose_avatar_alt.png"]:
            try:
                with open(filename, "rb") as f:
                    references[filename] = base64.standard_b64encode(f.read()).decode("utf-8")
            except:
                pass
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
        
        # Step 1: Generate visual description from Claude
        visual_description = self._generate_rose_description(meme_prompt, meme_caption)
        
        # Step 2: Generate image from DALL-E 3
        rose_image = self._generate_image_dalle3(visual_description)
        
        return rose_image
    
    def _generate_rose_description(self, meme_prompt, meme_caption):
        """Use Claude to generate detailed Rose visual description"""
        
        # Build message with Rose reference images
        content = [
            {
                "type": "text",
                "text": "Study these reference images of Rose to understand her appearance:"
            }
        ]
        
        # Add Rose reference images
        for filename, base64_data in self.rose_references.items():
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64_data
                }
            })
        
        # Add the generation prompt
        content.append({
            "type": "text",
            "text": f"""Based on these reference images of Rose, create a detailed visual description for an image generation AI.

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
   - Matching mood and energy

IMPORTANT RULES:
- Always keep the green bow in her hair
- Always keep her confident/sassy expression
- Never change her core appearance (hair color, style)
- Only change outfit, pose, setting, props
- Be very specific about colors, positions, and details

Return ONLY a 2-3 sentence visual description suitable for an image generator.
NO explanations, NO preamble, just the description."""
        })
        
        try:
            message = self.claude_client.messages.create(
                model="claude-opus-4-20250514",
                max_tokens=300,
                messages=[
                    {"role": "user", "content": content}
                ]
            )
            
            description = message.content[0].text.strip()
            return description
        except Exception as e:
            print(f"Error generating description: {e}")
            return "Rose, confident retro pinup character with orange hair and green bow, vintage aesthetic"
    
    def _generate_image_dalle3(self, rose_description):
        """Generate image using DALL-E 3 from Rose description"""
        
        # Create detailed prompt for DALL-E 3
        prompt = f"""Create a meme-style illustration based on this description:

{rose_description}

Style requirements:
- Comic/meme art style (cartoonish, vibrant colors)
- High quality illustration
- Professional meme aesthetic
- 1024x1024 resolution
- Bold outlines typical of meme art
- Colorful and eye-catching"""
        
        try:
            response = self.openai_client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )
            
            # Download the image
            image_url = response.data[0].url
            img_response = requests.get(image_url, timeout=10)
            
            if img_response.status_code == 200:
                return Image.open(BytesIO(img_response.content))
            else:
                return self._create_fallback_image(rose_description)
                
        except Exception as e:
            print(f"Error generating image with DALL-E 3: {e}")
            return self._create_fallback_image(rose_description)
    
    def compose_meme(self, rose_image, caption):
        """Compose final meme with Rose image + caption text"""
        
        # Resize Rose image if needed
        if rose_image.size != (900, 600):
            rose_image = rose_image.resize((900, 600), Image.Resampling.LANCZOS)
        
        # Create meme base
        meme = rose_image.convert('RGB')
        draw = ImageDraw.Draw(meme)
        
        # Load font
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48
            )
        except:
            font = ImageFont.load_default()
        
        # Add caption text
        wrapper = textwrap.TextWrapper(width=20)
        wrapped = '\n'.join(wrapper.wrap(text=caption))
        
        bbox = draw.textbbox((0, 0), wrapped, font=font)
        text_h = bbox[3] - bbox[1]
        text_w = bbox[2] - bbox[0]
        
        x = (900 - text_w) // 2
        y = (600 - text_h) // 2
        
        # Draw text with outline (black border for readability)
        outline_color = (0, 0, 0)
        text_color = (255, 255, 255)
        
        for adj_x in range(-3, 4):
            for adj_y in range(-3, 4):
                if adj_x != 0 or adj_y != 0:
                    draw.text((x + adj_x, y + adj_y), wrapped, font=font, fill=outline_color)
        
        draw.text((x, y), wrapped, font=font, fill=text_color)
        
        # Save to bytes
        img_bytes = BytesIO()
        meme.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        return img_bytes
    
    def _create_fallback_image(self, description):
        """Create fallback meme if image generation fails"""
        
        # Create simple fallback image
        img = Image.new('RGB', (900, 600), (26, 26, 46))
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32
            )
        except:
            font = ImageFont.load_default()
        
        # Add fallback text
        text = "Rose Meme\n(Image generation unavailable)"
        draw.text((50, 250), text, font=font, fill=(255, 200, 220))
        
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        return img
