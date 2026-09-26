from typing import Protocol

import discord

from mingati.errors import UserFacingError
from mingati.interactions import MingatiModal, MingatiView
from mingati.services.voice_rooms import MAX_NAME_LENGTH, MAX_USER_LIMIT, VoiceRoom

PICKER_TIMEOUT_SECONDS = 120
MAX_SELECT_OPTIONS = 25


class VoiceControls(Protocol):
    async def ensure_owner(self, interaction: discord.Interaction) -> None: ...
    async def rename(self, interaction: discord.Interaction, name: str) -> None: ...
    async def set_limit(self, interaction: discord.Interaction, limit: int) -> None: ...
    async def lock(self, interaction: discord.Interaction) -> None: ...
    async def unlock(self, interaction: discord.Interaction) -> None: ...
    async def invite(self, interaction: discord.Interaction, guest: discord.Member) -> None: ...
    async def transfer(
        self, interaction: discord.Interaction, new_owner: discord.Member
    ) -> None: ...
    async def close(self, interaction: discord.Interaction) -> None: ...
    def transfer_candidates(self, interaction: discord.Interaction) -> list[discord.Member]: ...


def build_panel_embed(room: VoiceRoom) -> discord.Embed:
    """Control panel shown in the room's text chat."""
    state = "🔒 Verrouillé" if room.is_locked else "🔓 Ouvert"
    return discord.Embed(
        title="🔊 Ton salon vocal",
        description=(
            f"👑 Propriétaire : <@{room.owner_id}>\n"
            f"État : {state}\n\n"
            "Seul le propriétaire peut utiliser ces boutons ou les commandes `/vocal`.\n"
            "Le salon disparaît dès qu'il est vide."
        ),
        color=discord.Color.blurple(),
    )


def parse_limit(raw: str) -> int:
    try:
        return int(raw.strip())
    except ValueError as error:
        raise UserFacingError(f"Indique un nombre entre 0 et {MAX_USER_LIMIT}.") from error


class RenameModal(MingatiModal, title="Renommer le salon"):
    new_name: discord.ui.TextInput["RenameModal"] = discord.ui.TextInput(
        label="Nouveau nom", max_length=MAX_NAME_LENGTH
    )

    def __init__(self, controls: VoiceControls) -> None:
        super().__init__()
        self.controls = controls

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.controls.rename(interaction, self.new_name.value)


class LimitModal(MingatiModal, title="Limite de places"):
    places: discord.ui.TextInput["LimitModal"] = discord.ui.TextInput(
        label="Nombre de places (0 = illimité)", max_length=len(str(MAX_USER_LIMIT))
    )

    def __init__(self, controls: VoiceControls) -> None:
        super().__init__()
        self.controls = controls

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.controls.set_limit(interaction, parse_limit(self.places.value))


class InvitePicker(MingatiView):
    def __init__(self, controls: VoiceControls) -> None:
        super().__init__(timeout=PICKER_TIMEOUT_SECONDS)
        self.controls = controls

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Qui veux-tu inviter ?")
    async def pick(self, interaction: discord.Interaction, select: discord.ui.UserSelect) -> None:
        guest = select.values[0]
        if not isinstance(guest, discord.Member):
            raise UserFacingError("Cette personne n'est pas sur le serveur.")
        await self.controls.invite(interaction, guest)


class TransferPicker(MingatiView):
    def __init__(self, controls: VoiceControls, candidates: list[discord.Member]) -> None:
        super().__init__(timeout=PICKER_TIMEOUT_SECONDS)
        self.controls = controls
        self.candidates = {member.id: member for member in candidates[:MAX_SELECT_OPTIONS]}
        select: discord.ui.Select[TransferPicker] = discord.ui.Select(
            placeholder="Nouveau propriétaire",
            options=[
                discord.SelectOption(label=member.display_name[:100], value=str(member.id))
                for member in self.candidates.values()
            ],
        )
        select.callback = self.pick
        self.add_item(select)
        self.select = select

    async def pick(self, interaction: discord.Interaction) -> None:
        new_owner = self.candidates.get(int(self.select.values[0]))
        if new_owner is None:
            raise UserFacingError("Cette personne n'est plus dans le salon.")
        await self.controls.transfer(interaction, new_owner)


class VoiceControlView(MingatiView):
    """Persistent panel: static custom_ids so buttons keep working after a restart."""

    def __init__(self, controls: VoiceControls) -> None:
        super().__init__(timeout=None)
        self.controls = controls

    @discord.ui.button(label="Renommer", emoji="✏️", custom_id="mingati:voice:rename", row=0)
    async def rename(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.controls.ensure_owner(interaction)
        await interaction.response.send_modal(RenameModal(self.controls))

    @discord.ui.button(label="Limite", emoji="🔢", custom_id="mingati:voice:limit", row=0)
    async def limit(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.controls.ensure_owner(interaction)
        await interaction.response.send_modal(LimitModal(self.controls))

    @discord.ui.button(label="Inviter", emoji="👥", custom_id="mingati:voice:invite", row=0)
    async def invite(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.controls.ensure_owner(interaction)
        await interaction.response.send_message(view=InvitePicker(self.controls), ephemeral=True)

    @discord.ui.button(label="Verrouiller", emoji="🔒", custom_id="mingati:voice:lock", row=1)
    async def lock(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.controls.lock(interaction)

    @discord.ui.button(label="Déverrouiller", emoji="🔓", custom_id="mingati:voice:unlock", row=1)
    async def unlock(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.controls.unlock(interaction)

    @discord.ui.button(label="Transférer", emoji="👑", custom_id="mingati:voice:transfer", row=1)
    async def transfer(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.controls.ensure_owner(interaction)
        candidates = self.controls.transfer_candidates(interaction)
        if not candidates:
            raise UserFacingError("Il n'y a personne d'autre dans le salon.")
        await interaction.response.send_message(
            view=TransferPicker(self.controls, candidates), ephemeral=True
        )

    @discord.ui.button(
        label="Fermer",
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
        custom_id="mingati:voice:close",
        row=1,
    )
    async def close(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.controls.close(interaction)
