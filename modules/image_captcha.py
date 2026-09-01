"""
Image captcha.

Flow:
  1. User clicks Verify -> we generate a code and render it as a distorted
     PNG in memory (no files saved to disk, no external API calls).
  2. The image is sent as a Discord attachment in an ephemeral message,
     alongside an "Enter Code" button (Discord modals can't contain images,
     so the image and the text-input step have to be two separate steps).
  3. Clicking "Enter Code" opens a modal with just a plain text field
     (unlike the text captcha, the code is NOT shown in the label here -
     the user has to read it off the image).
  4. Submitting the modal checks the answer against the same shared
     challenge store used by the text captcha.
"""

import io
import random
from pathlib import Path

import discord
from PIL import Image, ImageDraw, ImageFont

from core.base import VerificationModule
from core import service
from core.prechecks import passes_prechecks
from core.challenge_store import generate_code, store_challenge, check_answer

FONT_PATH = Path(__file__).parent.parent / "assets" / "fonts" / "DejaVuSans-Bold.ttf"
_IMAGE_SIZE = (220, 90)


def _load_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(FONT_PATH), size)
    except OSError:
        # Falls back to Pillow's built-in bitmap font if the bundled TTF
        # is ever missing - captcha still works, just less distorted-looking.
        return ImageFont.load_default()


def render_captcha_image(code: str) -> io.BytesIO:
    width, height = _IMAGE_SIZE
    image = Image.new("RGB", (width, height), (245, 245, 245))
    draw = ImageDraw.Draw(image)

    # Background noise lines (drawn first, so text renders on top of them)
    for _ in range(6):
        start = (random.randint(0, width), random.randint(0, height))
        end = (random.randint(0, width), random.randint(0, height))
        color = tuple(random.randint(180, 220) for _ in range(3))
        draw.line([start, end], fill=color, width=2)

    # Background speckle noise
    for _ in range(80):
        x, y = random.randint(0, width - 1), random.randint(0, height - 1)
        color = tuple(random.randint(180, 220) for _ in range(3))
        draw.point((x, y), fill=color)

    font = _load_font(42)
    char_spacing = width // (len(code) + 1)

    for i, char in enumerate(code):
        # Draw each character on its own transparent tile so it can be
        # rotated independently - this is what makes it hard for OCR/bots
        # to read reliably while still being readable by a human.
        char_img = Image.new("RGBA", (60, 70), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(char_img)
        color = tuple(random.randint(20, 90) for _ in range(3))
        char_draw.text((10, 5), char, font=font, fill=color)

        angle = random.randint(-25, 25)
        rotated = char_img.rotate(angle, expand=True, resample=Image.BICUBIC)

        x = char_spacing * (i + 1) - rotated.width // 2 + random.randint(-5, 5)
        y = (height - rotated.height) // 2 + random.randint(-8, 8)
        image.paste(rotated, (x, y), rotated)

    # Foreground noise lines drawn over the text - adds difficulty for bots
    # without making it unreadable for a human.
    for _ in range(3):
        start = (random.randint(0, width), random.randint(0, height))
        end = (random.randint(0, width), random.randint(0, height))
        color = tuple(random.randint(100, 160) for _ in range(3))
        draw.line([start, end], fill=color, width=1)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


class ImageCaptchaModal(discord.ui.Modal, title="Enter the code from the image"):
    answer = discord.ui.TextInput(
        label="Code", placeholder="e.g. AB3XZ9", max_length=10
    )

    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings

    async def on_submit(self, interaction: discord.Interaction):
        passed, reason = check_answer(interaction.user.id, self.answer.value)
        if passed:
            await service.grant_verified(interaction, self.settings)
        else:
            await service.deny_verified(interaction, self.settings, reason)


class EnterCodeButton(discord.ui.Button):
    def __init__(self, settings: dict):
        super().__init__(label="Enter Code", style=discord.ButtonStyle.primary)
        self.settings = settings

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ImageCaptchaModal(self.settings))


class EnterCodeView(discord.ui.View):
    """
    Short-lived, non-persistent view attached only to the ephemeral message
    containing the captcha image. It doesn't need to survive a bot restart -
    if the bot restarts mid-challenge, the user just clicks Verify again.
    """

    def __init__(self, settings: dict):
        super().__init__(timeout=300)
        self.add_item(EnterCodeButton(settings))


class ImageCaptchaButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Verify",
            style=discord.ButtonStyle.success,
            emoji="🖼️",
            custom_id="verify:image_captcha:click",
        )

    async def callback(self, interaction: discord.Interaction):
        from settings import settings_manager

        guild_settings = await settings_manager.get(interaction.guild_id)

        if not await passes_prechecks(interaction, guild_settings):
            return

        captcha_settings = guild_settings["method_settings"].get("captcha", {})
        code = generate_code(
            captcha_settings.get("length", 6),
            captcha_settings.get("type", "alphanumeric"),
        )
        store_challenge(interaction.user.id, code)

        image_buffer = render_captcha_image(code)
        file = discord.File(image_buffer, filename="captcha.png")

        await interaction.response.send_message(
            "Type the code shown in the image below.",
            file=file,
            view=EnterCodeView(guild_settings),
            ephemeral=True,
        )


class ImageCaptchaVerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # persists across restarts
        self.add_item(ImageCaptchaButton())


class ImageCaptchaVerification(VerificationModule):
    key = "image_captcha"
    display_name = "Captcha (image)"

    def build_entry_view(self, settings: dict) -> discord.ui.View:
        return ImageCaptchaVerificationView()
