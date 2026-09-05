import discord
from core.ui_base import BaseView, BaseModal
from tests.conftest import FakeInteraction


class _CrashingButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Crash")

    async def callback(self, interaction):
        raise ValueError("simulated bug")


class _TestView(BaseView):
    def __init__(self):
        super().__init__()
        self.add_item(_CrashingButton())


class _CrashingModal(BaseModal, title="Test"):
    field = discord.ui.TextInput(label="Field")

    async def on_submit(self, interaction):
        raise KeyError("simulated bug")


async def test_view_on_error_responds_when_no_response_sent_yet():
    view = _TestView()
    button = view.children[0]
    interaction = FakeInteraction()

    await view.on_error(interaction, ValueError("boom"), button)

    assert len(interaction.response.sent) == 1
    assert "went wrong" in interaction.response.sent[0].lower()


async def test_view_on_error_uses_followup_if_already_responded():
    view = _TestView()
    button = view.children[0]
    interaction = FakeInteraction()
    await interaction.response.send_message("already responded")

    await view.on_error(interaction, RuntimeError("boom"), button)

    assert len(interaction.followup.sent) == 1
    assert "went wrong" in interaction.followup.sent[0].lower()


async def test_modal_on_error_responds_to_user():
    modal = _CrashingModal()
    interaction = FakeInteraction()

    await modal.on_error(interaction, KeyError("boom"))

    assert len(interaction.response.sent) == 1
    assert "went wrong" in interaction.response.sent[0].lower()
