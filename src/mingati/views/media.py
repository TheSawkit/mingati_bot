from __future__ import annotations

from collections import defaultdict
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


async def _owner_only(owner_id: int, interaction: discord.Interaction) -> bool:
    if interaction.user.id == owner_id:
        return True
    await interaction.response.send_message(
        "Cette recherche appartient à quelqu'un d'autre.",
        ephemeral=True,
    )
    return False


def _media_type_label(media_type: MediaType) -> str:
    return {
        MediaType.MOVIE: "Film",
        MediaType.TV: "Série",
        MediaType.COLLECTION: "Saga",
    }[media_type]


def _format_runtime(minutes: int | None) -> str | None:
    if not minutes:
        return None
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours} h {mins:02d}"
    if hours:
        return f"{hours} h"
    return f"{mins} min"


def _truncate(text: str | None, limit: int) -> str:
    value = (text or "Aucune description disponible.").strip()
    return value if len(value) <= limit else f"{value[: limit - 1].rstrip()}…"


def _tmdb_footer() -> str:
    return "TMDB · API utilisée sans approbation ni certification de TMDB"


def build_search_embed(query: str, results: Sequence[MediaSearchResult]) -> discord.Embed:
    lines = [
        f"• **{result.title}** — {result.year or '?'} · {_media_type_label(result.media_type)}"
        for result in results[:MAX_RESULTS]
    ]
    embed = discord.Embed(
        title=f"Recherche : « {query} »",
        description="Choisis le bon titre dans le menu ci-dessous.\n\n" + "\n".join(lines),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=_tmdb_footer())
    return embed


def build_media_embed(media: MediaDetails) -> discord.Embed:
    title = f"{media.title} ({media.year})" if media.year else media.title
    metadata = [f"🎬 {_media_type_label(media.media_type)}"]
    if media.runtime_minutes:
        metadata.append(f"⏱ {_format_runtime(media.runtime_minutes)}")
    if media.rating is not None:
        metadata.append(f"⭐ {media.rating:.1f}/10")
    if media.genres:
        metadata.append("🎭 " + " · ".join(media.genres[:5]))
    if media.media_type == MediaType.TV and media.number_of_seasons is not None:
        seasons = media.number_of_seasons
        episodes = (
            f" · {media.number_of_episodes} épisodes"
            if media.number_of_episodes
            else ""
        )
        metadata.append(f"📺 {seasons} saison{'s' if seasons != 1 else ''}{episodes}")
    if media.original_title and media.original_title != media.title:
        metadata.append(f"Original : {media.original_title}")

    embed = discord.Embed(
        title=title,
        url=media.tmdb_url,
        description=_truncate(media.overview, 3500),
        color=discord.Color.blurple(),
    )
    if media.poster_url:
        embed.set_thumbnail(url=media.poster_url)
    embed.add_field(name="Infos", value="\n".join(metadata), inline=False)
    if media.collection_id and media.collection_name:
        embed.add_field(name="Saga", value=f"📚 {media.collection_name}", inline=False)
    embed.set_footer(text=_tmdb_footer())
    return embed


def _provider_lines(providers: Sequence[WatchProvider]) -> str:
    grouped: dict[str, list[WatchProvider]] = defaultdict(list)
    for provider in providers:
        grouped[provider.category].append(provider)

    sections: list[str] = []
    for category in ("Streaming", "Gratuit", "Avec publicité", "Location", "Achat"):
        items = grouped.get(category)
        if not items:
            continue
        sections.append(
            f"**{category}**\n"
            + "\n".join(f"• 🔗 [{item.provider_name}]({item.link})" for item in items)
        )
    return "\n\n".join(sections)


def build_sources_embed(
    media: MediaDetails,
    providers: Sequence[WatchProvider],
) -> discord.Embed:
    description = (
        _provider_lines(providers)
        if providers
        else "Aucun service de visionnage n'est indiqué pour la Belgique."
    )
    embed = discord.Embed(
        title=f"📺 Où regarder {media.title} ?",
        url=media.tmdb_url,
        description=description,
        color=discord.Color.green() if providers else discord.Color.orange(),
    )
    if providers:
        embed.add_field(name="Pays", value="🇧🇪 Belgique", inline=True)
        embed.add_field(name="Sources", value=str(len(providers)), inline=True)
    embed.set_footer(text="Disponibilités : JustWatch · " + _tmdb_footer())
    return embed


def build_collection_embed(collection: CollectionDetails) -> discord.Embed:
    parts = sorted(
        collection.parts,
        key=lambda item: (item.year is None, item.year or 0),
    )
    lines = [f"• **{part.title}** — {part.year or '?'}" for part in parts[:20]]
    embed = discord.Embed(
        title=collection.name,
        url=collection.tmdb_url,
        description=_truncate(collection.overview, 2500),
        color=discord.Color.blurple(),
    )
    if collection.poster_url:
        embed.set_thumbnail(url=collection.poster_url)
    embed.add_field(
        name=f"Films de la saga ({len(parts)})",
        value="\n".join(lines) or "Aucun film.",
        inline=False,
    )
    embed.set_footer(text=_tmdb_footer())
    return embed


def build_season_embed(media: MediaDetails, season: SeasonDetails) -> discord.Embed:
    lines = [
        f"**S{season.season_number:02d}E{episode.episode_number:02d}** — {episode.name}"
        for episode in season.episodes[:20]
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
        value="\n".join(lines) or "Aucun épisode.",
        inline=False,
    )
    embed.set_footer(text=_tmdb_footer())
    return embed


def build_episode_embed(
    media: MediaDetails,
    season: SeasonDetails,
    episode: Episode,
) -> discord.Embed:
    meta = [f"S{season.season_number:02d}E{episode.episode_number:02d}"]
    if episode.air_date:
        meta.append(episode.air_date)
    if episode.runtime_minutes:
        meta.append(f"⏱ {_format_runtime(episode.runtime_minutes)}")

    embed = discord.Embed(
        title=f"{media.title} — {episode.name}",
        url=media.tmdb_url,
        description=_truncate(episode.overview, 3000),
        color=discord.Color.blurple(),
    )
    if episode.still_url:
        embed.set_image(url=episode.still_url)
    embed.add_field(name="Épisode", value=" · ".join(meta), inline=False)
    embed.set_footer(text=_tmdb_footer())
    return embed


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
        query = str(self.query).strip()
        results = await self.service.search(self.http, query)
        if not results:
            await interaction.response.send_message(
                f"Aucun résultat pour « {query} ».",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=build_search_embed(query, results),
            view=SearchView(self.service, self.http, self.owner_id, results),
            ephemeral=True,
        )


class SearchView(MingatiView):
    def __init__(
        self,
        service: MediaService,
        http: ClientSession,
        owner_id: int,
        results: Sequence[MediaSearchResult],
    ) -> None:
        super().__init__(timeout=VIEW_TIMEOUT)
        self.service = service
        self.http = http
        self.owner_id = owner_id
        self.results = list(results[:MAX_RESULTS])
        self.add_item(ResultSelect(self))

    async def show_result(
        self,
        interaction: discord.Interaction,
        value: str,
    ) -> None:
        if not await _owner_only(self.owner_id, interaction):
            return
        result = self.results[int(value)]
        if result.media_type == MediaType.COLLECTION:
            collection = await self.service.collection(self.http, result.id)
            await interaction.response.edit_message(
                embed=build_collection_embed(collection),
                view=CollectionView(
                    self.service,
                    self.http,
                    self.owner_id,
                    collection,
                ),
            )
            return

        media = await self.service.details(self.http, result)
        await interaction.response.edit_message(
            embed=build_media_embed(media),
            view=DetailsView(self.service, self.http, self.owner_id, media),
        )


class ResultSelect(discord.ui.Select):
    def __init__(self, parent: SearchView) -> None:
        options = [
            discord.SelectOption(
                label=result.title[:100],
                description=(
                    f"{result.year or '?'} · {_media_type_label(result.media_type)}"
                )[:100],
                value=str(index),
            )
            for index, result in enumerate(parent.results)
        ]
        super().__init__(
            placeholder="Sélectionne un résultat…",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.parent_view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.parent_view.show_result(interaction, self.values[0])


class DetailsView(MingatiView):
    def __init__(
        self,
        service: MediaService,
        http: ClientSession,
        owner_id: int,
        media: MediaDetails,
    ) -> None:
        super().__init__(timeout=VIEW_TIMEOUT)
        self.service = service
        self.http = http
        self.owner_id = owner_id
        self.media = media

        sources = discord.ui.Button(
            label="Où regarder",
            emoji="📺",
            style=discord.ButtonStyle.success,
        )
        sources.callback = self.sources
        self.add_item(sources)

        if media.collection_id:
            saga = discord.ui.Button(label="Saga", emoji="📚")
            saga.callback = self.collection
            self.add_item(saga)

        if media.media_type == MediaType.TV and media.number_of_seasons:
            seasons = discord.ui.Button(label="Saisons", emoji="📺")
            seasons.callback = self.seasons
            self.add_item(seasons)

        search = discord.ui.Button(label="Nouvelle recherche", emoji="🔎")
        search.callback = self.new_search
        self.add_item(search)

    async def sources(self, interaction: discord.Interaction) -> None:
        if not await _owner_only(self.owner_id, interaction):
            return
        await interaction.response.defer()
        providers = await self.service.providers(self.http, self.media)
        await interaction.message.edit(
            embed=build_sources_embed(self.media, providers),
            view=SourcesView(
                self.service,
                self.http,
                self.owner_id,
                self.media,
            ),
        )

    async def collection(self, interaction: discord.Interaction) -> None:
        if not await _owner_only(self.owner_id, interaction):
            return
        if not self.media.collection_id:
            return
        await interaction.response.defer()
        collection = await self.service.collection(self.http, self.media.collection_id)
        await interaction.message.edit(
            embed=build_collection_embed(collection),
            view=CollectionView(
                self.service,
                self.http,
                self.owner_id,
                collection,
            ),
        )

    async def seasons(self, interaction: discord.Interaction) -> None:
        if not await _owner_only(self.owner_id, interaction):
            return
        await interaction.response.edit_message(
            embed=build_media_embed(self.media),
            view=SeasonListView(self.service, self.http, self.owner_id, self.media),
        )

    async def new_search(self, interaction: discord.Interaction) -> None:
        if not await _owner_only(self.owner_id, interaction):
            return
        await interaction.response.send_modal(
            WatchModal(self.service, self.http, self.owner_id)
        )


class SourcesView(MingatiView):
    def __init__(
        self,
        service: MediaService,
        http: ClientSession,
        owner_id: int,
        media: MediaDetails,
    ) -> None:
        super().__init__(timeout=VIEW_TIMEOUT)
        self.service = service
        self.http = http
        self.owner_id = owner_id
        self.media = media

        back = discord.ui.Button(label="Retour", emoji="↩️")
        back.callback = self.back
        self.add_item(back)

    async def back(self, interaction: discord.Interaction) -> None:
        if not await _owner_only(self.owner_id, interaction):
            return
        await interaction.response.edit_message(
            embed=build_media_embed(self.media),
            view=DetailsView(self.service, self.http, self.owner_id, self.media),
        )


class CollectionView(MingatiView):
    def __init__(
        self,
        service: MediaService,
        http: ClientSession,
        owner_id: int,
        collection: CollectionDetails,
    ) -> None:
        super().__init__(timeout=VIEW_TIMEOUT)
        self.service = service
        self.http = http
        self.owner_id = owner_id
        self.collection = collection
        self.results = list(collection.parts[:MAX_RESULTS])
        if self.results:
            self.add_item(CollectionSelect(self))

        search = discord.ui.Button(label="Nouvelle recherche", emoji="🔎")
        search.callback = self.new_search
        self.add_item(search)

    async def choose(self, interaction: discord.Interaction, value: str) -> None:
        if not await _owner_only(self.owner_id, interaction):
            return
        result = self.results[int(value)]
        media = await self.service.details(self.http, result)
        await interaction.response.edit_message(
            embed=build_media_embed(media),
            view=DetailsView(self.service, self.http, self.owner_id, media),
        )

    async def new_search(self, interaction: discord.Interaction) -> None:
        if not await _owner_only(self.owner_id, interaction):
            return
        await interaction.response.send_modal(
            WatchModal(self.service, self.http, self.owner_id)
        )


class CollectionSelect(discord.ui.Select):
    def __init__(self, parent: CollectionView) -> None:
        options = [
            discord.SelectOption(
                label=part.title[:100],
                description=f"{part.year or '?'} · Film"[:100],
                value=str(index),
            )
            for index, part in enumerate(parent.results)
        ]
        super().__init__(
            placeholder="Choisis un film de la saga…",
            options=options,
        )
        self.parent_view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.parent_view.choose(interaction, self.values[0])


class SeasonListView(MingatiView):
    def __init__(
        self,
        service: MediaService,
        http: ClientSession,
        owner_id: int,
        media: MediaDetails,
    ) -> None:
        super().__init__(timeout=VIEW_TIMEOUT)
        self.service = service
        self.http = http
        self.owner_id = owner_id
        self.media = media
        self.add_item(SeasonSelect(self))

        back = discord.ui.Button(label="Retour", emoji="↩️")
        back.callback = self.back
        self.add_item(back)

    async def choose(self, interaction: discord.Interaction, season_number: int) -> None:
        if not await _owner_only(self.owner_id, interaction):
            return
        await interaction.response.defer()
        season = await self.service.season(self.http, self.media.id, season_number)
        await interaction.message.edit(
            embed=build_season_embed(self.media, season),
            view=SeasonView(self.service, self.http, self.owner_id, self.media, season),
        )

    async def back(self, interaction: discord.Interaction) -> None:
        if not await _owner_only(self.owner_id, interaction):
            return
        await interaction.response.edit_message(
            embed=build_media_embed(self.media),
            view=DetailsView(self.service, self.http, self.owner_id, self.media),
        )


class SeasonSelect(discord.ui.Select):
    def __init__(self, parent: SeasonListView) -> None:
        count = min(parent.media.number_of_seasons or 0, MAX_RESULTS)
        options = [
            discord.SelectOption(
                label=f"Saison {number}",
                value=str(number),
            )
            for number in range(1, count + 1)
        ]
        super().__init__(placeholder="Choisis une saison…", options=options)
        self.parent_view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.parent_view.choose(interaction, int(self.values[0]))


class SeasonView(MingatiView):
    def __init__(
        self,
        service: MediaService,
        http: ClientSession,
        owner_id: int,
        media: MediaDetails,
        season: SeasonDetails,
    ) -> None:
        super().__init__(timeout=VIEW_TIMEOUT)
        self.service = service
        self.http = http
        self.owner_id = owner_id
        self.media = media
        self.season = season

        if season.episodes:
            self.add_item(EpisodeSelect(self))

        sources = discord.ui.Button(
            label="Sources de visionnage",
            emoji="📺",
            style=discord.ButtonStyle.success,
        )
        sources.callback = self.sources
        self.add_item(sources)

        back = discord.ui.Button(label="Saisons", emoji="↩️")
        back.callback = self.back
        self.add_item(back)

    async def choose_episode(self, interaction: discord.Interaction, value: str) -> None:
        if not await _owner_only(self.owner_id, interaction):
            return
        episode = self.season.episodes[int(value)]
        await interaction.response.edit_message(
            embed=build_episode_embed(self.media, self.season, episode),
            view=EpisodeView(
                self.service,
                self.http,
                self.owner_id,
                self.media,
                self.season,
                episode,
            ),
        )

    async def sources(self, interaction: discord.Interaction) -> None:
        if not await _owner_only(self.owner_id, interaction):
            return
        await interaction.response.defer()
        providers = await self.service.providers(self.http, self.media)
        await interaction.message.edit(
            embed=build_sources_embed(self.media, providers),
            view=EpisodeSourcesView(
                self.service,
                self.http,
                self.owner_id,
                self.media,
                self.season,
            ),
        )

    async def back(self, interaction: discord.Interaction) -> None:
        if not await _owner_only(self.owner_id, interaction):
            return
        await interaction.response.edit_message(
            embed=build_media_embed(self.media),
            view=SeasonListView(self.service, self.http, self.owner_id, self.media),
        )


class EpisodeSelect(discord.ui.Select):
    def __init__(self, parent: SeasonView) -> None:
        options = [
            discord.SelectOption(
                label=f"E{episode.episode_number:02d} · {episode.name}"[:100],
                description=(episode.air_date or "Date inconnue")[:100],
                value=str(index),
            )
            for index, episode in enumerate(parent.season.episodes[:MAX_RESULTS])
        ]
        super().__init__(placeholder="Choisis un épisode…", options=options)
        self.parent_view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.parent_view.choose_episode(interaction, self.values[0])


class EpisodeView(MingatiView):
    def __init__(
        self,
        service: MediaService,
        http: ClientSession,
        owner_id: int,
        media: MediaDetails,
        season: SeasonDetails,
        episode: Episode,
    ) -> None:
        super().__init__(timeout=VIEW_TIMEOUT)
        self.service = service
        self.http = http
        self.owner_id = owner_id
        self.media = media
        self.season = season
        self.episode = episode

        sources = discord.ui.Button(
            label="Sources de visionnage",
            emoji="📺",
            style=discord.ButtonStyle.success,
        )
        sources.callback = self.sources
        self.add_item(sources)

        back = discord.ui.Button(label="Épisodes", emoji="↩️")
        back.callback = self.back
        self.add_item(back)

    async def sources(self, interaction: discord.Interaction) -> None:
        if not await _owner_only(self.owner_id, interaction):
            return
        await interaction.response.defer()
        providers = await self.service.providers(self.http, self.media)
        await interaction.message.edit(
            embed=build_sources_embed(self.media, providers),
            view=EpisodeSourcesView(
                self.service,
                self.http,
                self.owner_id,
                self.media,
                self.season,
            ),
        )

    async def back(self, interaction: discord.Interaction) -> None:
        if not await _owner_only(self.owner_id, interaction):
            return
        await interaction.response.edit_message(
            embed=build_season_embed(self.media, self.season),
            view=SeasonView(self.service, self.http, self.owner_id, self.media, self.season),
        )


class EpisodeSourcesView(MingatiView):
    def __init__(
        self,
        service: MediaService,
        http: ClientSession,
        owner_id: int,
        media: MediaDetails,
        season: SeasonDetails,
    ) -> None:
        super().__init__(timeout=VIEW_TIMEOUT)
        self.service = service
        self.http = http
        self.owner_id = owner_id
        self.media = media
        self.season = season

        back = discord.ui.Button(label="Retour", emoji="↩️")
        back.callback = self.back
        self.add_item(back)

    async def back(self, interaction: discord.Interaction) -> None:
        if not await _owner_only(self.owner_id, interaction):
            return
        await interaction.response.edit_message(
            embed=build_season_embed(self.media, self.season),
            view=SeasonView(self.service, self.http, self.owner_id, self.media, self.season),
        )
