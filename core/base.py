"""
VerificationModule - the shared interface every verification method implements.

The bot's core logic (posting the verification message, restoring buttons on
restart) never needs to know *how* a method works internally - it just asks
the module for a View to attach to a message.

Each module is responsible for:
  - presenting whatever UI it needs (button, modal, etc.)
  - deciding when a user has passed or failed
  - calling core.service.grant_verified() / deny_verified() to finish the job

This keeps role-assignment, logging, and error handling in one shared place
(core/service.py) instead of duplicated per module.
"""

from abc import ABC, abstractmethod
import discord


class VerificationModule(ABC):
    key: str  # matches settings["method"], e.g. "button", "captcha"
    display_name: str  # shown in UI / logs, e.g. "Button", "Captcha"

    @abstractmethod
    def build_entry_view(self, settings: dict) -> discord.ui.View:
        """
        Return the discord.ui.View to attach to the verification message
        posted in the server's verify channel. Must be a persistent view
        (timeout=None, static custom_id on its components) so it keeps
        working after the bot restarts.
        """
        raise NotImplementedError

    def get_persistent_view(self) -> discord.ui.View:
        """
        Return an instance of the same view used in build_entry_view(),
        for the bot to re-register on startup via bot.add_view().
        Defaults to calling build_entry_view() with an empty settings,
        since persistent views must not depend on per-guild data at
        construction time - only at interaction time.
        """
        return self.build_entry_view(settings={})
