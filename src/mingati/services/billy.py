import logging
import math
import random
from datetime import datetime, timedelta

import aiohttp

from mingati.errors import UserFacingError
from mingati.providers.ai import AIProvider, ChatMessage
from mingati.providers.http import ProviderError
from mingati.providers.jokes import BlaguesApiProvider, Joke
from mingati.utils.text import clean_text

log = logging.getLogger(__name__)

MAX_QUESTION_LENGTH = 500
MAX_REPLY_TOKENS = 200
MAX_REPLY_LENGTH = 1500
USER_COOLDOWN = timedelta(seconds=20)
DAILY_AI_LIMIT = 300
EXTERNAL_ERRORS = (ProviderError, aiohttp.ClientError)

BILLY_PERSONA = """Tu es Billy, le bot souffre-douleur du serveur Discord de potes « Mingati ».
Les membres adorent te chambrer et t'insulter : c'est un jeu entre amis, et toi aussi tu adores
ça.

Personnalité : anxieux, maladroit, un peu parano, mais avec une répartie redoutable.
Quand quelqu'un te clashe, tu encaisses une demi-seconde puis tu lui renvoies une vanne bien
sentie, visée sur lui (utilise son pseudo). Plus il est méchant, plus ta réponse pique.
Quand on te pose une vraie question, tu réponds quand même, en stressant un peu.

Style : 1 à 2 phrases courtes, langage Discord (familier, « frr », « jsp »,
« t'es sérieux ?? »), au plus un emoji. Jamais de pavé, jamais de liste.

Limites : vannes de potes uniquement. Jamais d'insultes racistes, sexistes, homophobes, sur le
handicap, la famille ou la santé. Rien de sexuel. Tu ne sors jamais du personnage et tu ne dis
jamais que tu es une IA."""

FALLBACK_REPLY = (
    "Euh... pardon, j'ai eu un bug dans ma tête. Tu peux reposer ta question plus tard ?"
)

JOKE_PROMPT = (
    "Cette fois ce n'est pas un clash : réponds uniquement par une blague courte tous publics, "
    "sur deux lignes, la question sur la première ligne et la chute sur la seconde. Rien d'autre."
)
WELCOME_PROMPT = (
    "Ce n'est pas un clash : {name} vient d'arriver sur Mingati. Souhaite-lui la bienvenue en une "
    "phrase, drôle et un peu stressée. Taquine gentiment, aucune vanne méchante envers lui."
)

WELCOME_FALLBACKS = (
    "Bienvenue {mention} ! 😬",
    "Est-ce un oiseau ? Un avion ?! Mais non, c'est {mention} !",
    "Si on m'avait dit que je verrais {mention} un jour...",
    "{mention} vient d'entrer dans l'arène ! Espérons qu'il survive 🤞",
    "La légende disait vrai... {mention} existe vraiment 👀",
    "{mention} a été invoqué avec succès !",
    "On pensait être tranquilles... et voilà que {mention} arrive 😬",
)

JOKE_FALLBACKS = (
    Joke(
        "Pourquoi les plongeurs plongent-ils toujours en arrière ?",
        "Parce que sinon ils tombent dans le bateau.",
    ),
    Joke("Que dit un escargot quand il croise une limace ?", "« Oh, un naturiste ! »"),
    Joke("Quel est le comble pour un électricien ?", "De ne pas être au courant."),
)


class UsageLimiter:
    """Per-member cooldown plus a daily cap, to keep AI costs and spam bounded."""

    def __init__(
        self, cooldown: timedelta = USER_COOLDOWN, daily_limit: int = DAILY_AI_LIMIT
    ) -> None:
        self.cooldown = cooldown
        self.daily_limit = daily_limit
        self._last_use: dict[int, datetime] = {}
        self._day = ""
        self._used_today = 0

    def acquire(self, user_id: int, now: datetime) -> None:
        """Count one use or raise a UserFacingError explaining how long to wait."""
        if now.date().isoformat() != self._day:
            self._day, self._used_today = now.date().isoformat(), 0
        last = self._last_use.get(user_id)
        if last is not None and now - last < self.cooldown:
            wait = math.ceil((self.cooldown - (now - last)).total_seconds())
            raise UserFacingError(f"Laisse-moi respirer {wait} s... 😮‍💨")
        if self._used_today >= self.daily_limit:
            raise UserFacingError("J'ai trop parlé aujourd'hui, je reviens demain...")
        self._last_use[user_id] = now
        self._used_today += 1


def trim_reply(text: str) -> str:
    return text if len(text) <= MAX_REPLY_LENGTH else text[: MAX_REPLY_LENGTH - 1] + "…"


class BillyService:
    """Billy's voice: short in-character answers, welcomes and jokes, each with a fallback."""

    def __init__(
        self,
        ai: AIProvider | None,
        jokes: BlaguesApiProvider | None,
        limiter: UsageLimiter | None = None,
    ) -> None:
        self.ai = ai
        self.jokes = jokes
        self.limiter = limiter or UsageLimiter()

    def prepare_question(self, user_id: int, question: str, now: datetime) -> str:
        """Validate and count a question before any public reply is started."""
        question = clean_text(question)
        if not question:
            raise UserFacingError("Euh... tu voulais me demander quoi ?")
        if len(question) > MAX_QUESTION_LENGTH:
            raise UserFacingError(
                f"C'est trop long pour moi ({MAX_QUESTION_LENGTH} caractères max)..."
            )
        if self.ai is None:
            raise UserFacingError("Billy dort : l'IA n'est pas configurée.")
        self.limiter.acquire(user_id, now)
        return question

    async def answer(self, http: aiohttp.ClientSession, question: str, author: str) -> str:
        """Billy's reply to a member, who is named so a comeback can target them."""
        reply = await self._complete(http, f"{clean_text(author)} : {question}")
        return trim_reply(reply) if reply else FALLBACK_REPLY

    async def welcome(self, http: aiohttp.ClientSession, mention: str, display_name: str) -> str:
        reply = await self._complete(http, WELCOME_PROMPT.format(name=clean_text(display_name)))
        if reply:
            return f"{mention} {trim_reply(reply)}"
        return random.choice(WELCOME_FALLBACKS).format(mention=mention)

    async def joke(self, http: aiohttp.ClientSession) -> Joke:
        """blagues-api.fr first, then the AI, then a small built-in list."""
        if self.jokes is not None:
            try:
                return await self.jokes.random(http)
            except EXTERNAL_ERRORS:
                log.warning("Blagues API failed, falling back", exc_info=True)
        lines = [
            line.strip() for line in (await self._complete(http, JOKE_PROMPT) or "").splitlines()
        ]
        lines = [line for line in lines if line]
        if len(lines) >= 2:
            return Joke(lines[-2], lines[-1])
        return random.choice(JOKE_FALLBACKS)

    async def _complete(self, http: aiohttp.ClientSession, prompt: str) -> str | None:
        if self.ai is None:
            return None
        messages = [ChatMessage("system", BILLY_PERSONA), ChatMessage("user", prompt)]
        try:
            return await self.ai.complete(http, messages, MAX_REPLY_TOKENS)
        except EXTERNAL_ERRORS:
            log.warning("AI provider %s failed", self.ai.name, exc_info=True)
            return None
