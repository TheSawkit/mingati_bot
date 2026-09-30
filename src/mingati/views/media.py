from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import discord

from mingati.interactions import MingatiModal, MingatiView
from mingati.providers.media.tmdb import (
    CollectionDetails,
    Episode,
    MediaDetails,
    MediaSearchResult,
    MediaType,
    SeasonDetails,
    WatchProvider,
)
from mingati.services.media import MediaService

if TYPE_CHECKING:
    from aiohttp import ClientSession

MAX_RESULTS = 25
VIEW_TIMEOUT = 10 * 60


async def send_watch_search(
    interaction: discord.Interaction,
    service: MediaService,
    http: ClientSession,
    owner_id: int,
    query: str,
) -> None:
    query = query.strip()
    await interaction.response.defer(ephemeral=True, thinking=True)
    results = await service.search(http, query)
    if not results:
        await interaction.followup.send(
            f"Aucun résultat pour « {query} ».",
            ephemeral=True,
        )
        return

    view = WatchView(service, http, owner_id)
    view.show_search(query, results)
    await interaction.followup.send(
        embed=view.embed,
        view=view,
        ephemeral=True,
    )


def _type_label(media_type: MediaType) -> str:
    return "Film" if media_type == MediaType.MOVIE else "Série"


def _runtime(minutes: int | None) -> str | None:
    if not minutes:
        return None
    hours, mins = divmod(minutes, 60)
    if hours:
        return f"{hours} h {mins:02d}" if mins else f"{hours} h"
    return f"{mins} min"


def _truncate(value: str | None, limit: int) -> str:
    text = (value or "Aucune description disponible.").strip()
    return text if len(text) <= limit else f"{text[: limit - 1].rstrip()}…"


def _footer() -> str:
    return "Données TMDB · Disponibilités JustWatch"


def _title(media: MediaDetails) -> str:
    return f"{media.title} ({media.year})" if media.year else media.title


def build_search_embed(query: str, results: Sequence[MediaSearchResult]) -> discord.Embed:
    lines = [
        f"• **{result.title}** — {result.year or '?'} · {_type_label(result.media_type)}"
        for result in results
    ]
    return discord.Embed(
        title=f"Recherche : « {query} »",
        description="Sélectionne le titre voulu dans le menu.\\n\\n" + "\\n".join(lines),
        color=discord.Color.blurple(),
    ).set_footer(text=_footer())


def build_details_embed(media: MediaDetails) -> discord.Embed:
    info = [f"🎬 {_type_label(media.media_type)}"]
    if media.runtime_minutes:
        info.append(f"⏱ {_runtime(media.runtime_minutes)}")
    if media.rating is not None:
        info.append(f"⭐ {media.rating:.1f}/10")
    if media.genres:
        info.append("🎭 " + " · ".join(media.genres[:5]))
    if media.media_type == MediaType.TV and media.seasons:
        episode_text = f" · {media.episodes} épisodes" if media.episodes else ""
        info.append(f"📺 {media.seasons} saison{'s' if media.seasons != 1 else ''}{episode_text}")
    if media.original_title and media.original_title != media.title:
        info.append(f"Original : {media.original_title}")

    embed = discord.Embed(
        title=_title(media),
        url=media.tmdb_url,
        description=_truncate(media.overview, 3500),
        color=discord.Color.blurple(),
    )
    if media.poster_url:
        embed.set_thumbnail(url=media.poster_url)
    embed.add_field(name="Infos", value="\\n".join(info), inline=False)
    if media.collection_name:
        embed.add_field(name="Saga", value=f"📚 {media.collection_name}", inline=False)
    return embed.set_footer(text=_footer())


def build_collection_embed(collection: CollectionDetails) -> discord.Embed:
    films = sorted(collection.films, key=lambda item: item.year or 9999)
    lines = [f"• **{film.title}** — {film.year or '?'}" for film in films[:MAX_RESULTS]]
    embed = discord.Embed(
        title=collection.name,
        url=collection.tmdb_url,
        description=_truncate(collection.overview, 2500),
        color=discord.Color.blurple(),
    )
    if collection.poster_url:
        embed.set_thumbnail(url=collection.poster_url)
    embed.add_field(
        name=f"Films ({len(films)})",
        value="\\n".join(lines) or "Aucun film.",
        inline=False,
    )
    return embed.set_footer(text=_footer())


def build_season_embed(media: MediaDetails, season: SeasonDetails) -> discord.Embed:
    lines = [
        f"**S{season.number:02d}E{episode.number:02d}** — {episode.name}"
        for episode in season.episodes[:MAX_RESULTS]
    ]
    embed = discord.Embed(
        title=f"{media.title} — {season.name}",
        url=media.tmdb_url,
        description=_truncate(season.overview, 2500),
        color=discord.Color.blurple(),
    )
    if season.poster_url:
        embed.set_thumbnail(url=season.poster_url)
    embed.add_field(
        name=f"Épisodes ({len(season.episodes)})",
        value="\\n".join(lines) or "Aucun épisode.",
        inline=False,
    )
    return embed.set_footer(text=_footer())


def build_episode_embed(
    media: MediaDetails,
    season: SeasonDetails,
    episode: Episode,
) -> discord.Embed:
    meta = [f"S{season.number:02d}E{episode.number:02d}"]
    if episode.air_date:
        meta.append(episode.air_date)
    if episode.runtime_minutes:
        meta.append(f"⏱ {_runtime(episode.runtime_minutes)}")

    embed = discord.Embed(
        title=f"{media.title} — {episode.name}",
        url=media.tmdb_url,
        description=_truncate(episode.overview, 3000),
        color=discord.Color.blurple(),
    )
    if episode.still_url:
        embed.set_image(url=episode.still_url)
    embed.add_field(name="Épisode", value=" · ".join(meta), inline=False)
    return embed.set_footer(text=_footer())


def build_sources_embed(
    media: MediaDetails,
    providers: Sequence[WatchProvider],
) -> discord.Embed:
    lines = [
        f"• 🔗 [{provider.name}]({provider.link}) — {provider.category}" for provider in providers
    ]
    description = "\\n".join(lines)
    if not description:
        description = "Aucun service de visionnage trouvé pour la Belgique."
    return discord.Embed(
        title=f"📺 Où regarder {media.title} ?",
        url=media.tmdb_url,
        description=description,
        color=discord.Color.green() if providers else discord.Color.orange(),
    ).set_footer(text=_footer())


class WatchModal(MingatiModal, title="Chercher un film ou une série"):
    query = discord.ui.TextInput(
        label="Titre",
        placeholder="Ex. Interstellar, The Last of Us, Harry Potter…",
        min_length=2,
        max_length=100,
    )

    def __init__(
        self,
        service: MediaService,
        http: ClientSession,
        owner_id: int,
    ) -> None:
        super().__init__()
        self.service = service
        self.http = http
        self.owner_id = owner_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await send_watch_search(
            interaction,
            self.service,
            self.http,
            self.owner_id,
            str(self.query),
        )


class WatchView(MingatiView):
    """One short-lived state machine for a user's media search."""

    def __init__(
        self,
        service: MediaService,
        http: ClientSession,
        owner_id: int,
    ) -> None:
        super().__init__(timeout=VIEW_TIMEOUT)
        self.service = service
        self.http = http
        self.owner_id = owner_id
        self.embed = discord.Embed()
        self.results: list[MediaSearchResult] = []
        self.media: MediaDetails | None = None
        self.collection: CollectionDetails | None = None
        self.season: SeasonDetails | None = None
        self.episode: Episode | None = None

    def show_search(
        self,
        query: str,
        results: Sequence[MediaSearchResult],
    ) -> None:
        self.results = list(results[:MAX_RESULTS])
        self.media = None
        self.collection = None
        self.season = None
        self.episode = None
        self.clear_items()
        self.add_item(MediaSelect(self))
        self.embed = build_search_embed(query, self.results)

    def show_details(self, media: MediaDetails) -> None:
        self.media = media
        self.collection = None
        self.season = None
        self.episode = None
        self.clear_items()
        self._add_button("📺 Où regarder", self.sources, discord.ButtonStyle.success)
        if media.collection_id:
            self._add_button("📚 Saga", self.open_collection)
        if media.media_type == MediaType.TV and media.seasons:
            self._add_button("Saisons", self.open_seasons)
        self._add_button("🔎 Nouvelle recherche", self.new_search)
        self.embed = build_details_embed(media)

    def show_collection(self, collection: CollectionDetails) -> None:
        self.collection = collection
        self.results = list(collection.films[:MAX_RESULTS])
        self.clear_items()
        if self.results:
            self.add_item(CollectionSelect(self))
        self._add_button("↩️ Retour", self.back_to_details)
        self.embed = build_collection_embed(collection)

    def show_seasons(self) -> None:
        self.clear_items()
        self.add_item(SeasonSelect(self))
        self._add_button("↩️ Retour", self.back_to_details)
        self.embed = build_details_embed(self.media) if self.media else discord.Embed()

    def show_season(self, season: SeasonDetails) -> None:
        self.season = season
        self.episode = None
        self.clear_items()
        if season.episodes:
            self.add_item(EpisodeSelect(self))
        self._add_button("↩️ Saisons", self.open_seasons)
        self.embed = build_season_embed(self.media, season) if self.media else discord.Embed()

    def show_episode(self, episode: Episode) -> None:
        self.episode = episode
        self.clear_items()
        self._add_button("📺 Sources", self.sources, discord.ButtonStyle.success)
        self._add_button("↩️ Épisodes", self.back_to_season)
        if self.media and self.season:
            self.embed = build_episode_embed(self.media, self.season, episode)

    def show_sources(self, providers: Sequence[WatchProvider]) -> None:
        self.clear_items()
        self._add_button("↩️ Retour", self.back_from_sources)
        if self.media:
            self.embed = build_sources_embed(self.media, providers)

    def _add_button(
        self,
        label: str,
        callback,
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
    ) -> None:
        button = discord.ui.Button(label=label[:80], style=style)
        button.callback = callback
        self.add_item(button)

    async def _check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            "Cette recherche appartient à quelqu'un d'autre.",
            ephemeral=True,
        )
        return False

    async def select_result(self, interaction: discord.Interaction, index: int) -> None:
        if not await self._check(interaction):
            return
        await interaction.response.defer()
        self.show_details(await self.service.details(self.http, self.results[index]))
        await interaction.edit_original_response(embed=self.embed, view=self)

    async def open_collection(self, interaction: discord.Interaction) -> None:
        if not await self._check(interaction):
            return
        if not self.media or not self.media.collection_id:
            return
        await interaction.response.defer()
        self.show_collection(await self.service.collection(self.http, self.media.collection_id))
        await interaction.edit_original_response(embed=self.embed, view=self)

    async def open_seasons(self, interaction: discord.Interaction) -> None:
        if not await self._check(interaction):
            return
        self.show_seasons()
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def select_season(self, interaction: discord.Interaction, number: int) -> None:
        if not await self._check(interaction):
            return
        await interaction.response.defer()
        if not self.media:
            return
        self.show_season(await self.service.season(self.http, self.media.id, number))
        await interaction.edit_original_response(embed=self.embed, view=self)

    async def select_episode(self, interaction: discord.Interaction, index: int) -> None:
        if not await self._check(interaction):
            return
        if not self.season:
            return
        self.show_episode(self.season.episodes[index])
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def sources(self, interaction: discord.Interaction) -> None:
        if not await self._check(interaction):
            return
        if not self.media:
            return
        await interaction.response.defer()
        self.show_sources(await self.service.providers(self.http, self.media))
        await interaction.edit_original_response(embed=self.embed, view=self)

    async def back_from_sources(self, interaction: discord.Interaction) -> None:
        if not await self._check(interaction):
            return
        if self.episode and self.season and self.media:
            self.show_episode(self.episode)
        elif self.media:
            self.show_details(self.media)
        else:
            return
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def back_to_details(self, interaction: discord.Interaction) -> None:
        if not await self._check(interaction):
            return
        if not self.media:
            return
        self.show_details(self.media)
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def back_to_season(self, interaction: discord.Interaction) -> None:
        if not await self._check(interaction):
            return
        if not self.season:
            return
        self.show_season(self.season)
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def new_search(self, interaction: discord.Interaction) -> None:
        if not await self._check(interaction):
            return
        await interaction.response.send_modal(WatchModal(self.service, self.http, self.owner_id))


class MediaSelect(discord.ui.Select):
    def __init__(self, view: WatchView) -> None:
        options = [
            discord.SelectOption(
                label=result.title[:100],
                description=(f"{result.year or '?'} · {_type_label(result.media_type)}")[:100],
                value=str(index),
            )
            for index, result in enumerate(view.results)
        ]
        super().__init__(
            placeholder="Choisis un film ou une série…",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.watch_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.watch_view.select_result(interaction, int(self.values[0]))


class CollectionSelect(discord.ui.Select):
    def __init__(self, view: WatchView) -> None:
        options = [
            discord.SelectOption(
                label=film.title[:100],
                description=f"{film.year or '?'} · Film"[:100],
                value=str(index),
            )
            for index, film in enumerate(view.collection.films[:MAX_RESULTS])
        ]
        super().__init__(placeholder="Choisis un film de la saga…", options=options)
        self.watch_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        index = int(self.values[0])
        await self.watch_view.select_result(interaction, index)


class SeasonSelect(discord.ui.Select):
    def __init__(self, view: WatchView) -> None:
        count = min(view.media.seasons or 0, MAX_RESULTS)
        options = [
            discord.SelectOption(label=f"Saison {number}", value=str(number))
            for number in range(1, count + 1)
        ]
        super().__init__(placeholder="Choisis une saison…", options=options)
        self.watch_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.watch_view.select_season(interaction, int(self.values[0]))


class EpisodeSelect(discord.ui.Select):
    def __init__(self, view: WatchView) -> None:
        options = [
            discord.SelectOption(
                label=f"E{episode.number:02d} · {episode.name}"[:100],
                description=(episode.air_date or "Date inconnue")[:100],
                value=str(index),
            )
            for index, episode in enumerate(view.season.episodes[:MAX_RESULTS])
        ]
        super().__init__(placeholder="Choisis un épisode…", options=options)
        self.watch_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.watch_view.select_episode(interaction, int(self.values[0]))
