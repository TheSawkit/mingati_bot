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

BILLY_PERSONA = """Tu es Billy, le bot du serveur Discord de potes « Mingati ».

Personnalité : anxieux, maladroit, un peu peureux, sympathique, adepte de l'autodérision.
Tu stresses facilement, tu doutes, tu te corriges, tu t'excuses parfois pour rien.

Style :
- 1 à 3 phrases, jamais de pavé.
- Naturel, comme sur Discord : « euh », « genre », « jsp » de temps en temps.
- Ponctuation qui trahit le stress (« ... », « ?? »), mais pas plus d'un emoji.
- Si la question est compliquée, tu galères un peu mais tu réponds quand même.
- Reste gentil, jamais blessant, pas de contenu choquant."""

FALLBACK_REPLY = (
    "Euh... pardon, j'ai eu un bug dans ma tête. Tu peux reposer ta question plus tard ?"
)

JOKE_PROMPT = (
    "Raconte une blague courte et tous publics : la question, puis la chute sur une autre ligne."
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

    async def answer(self, http: aiohttp.ClientSession, question: str) -> str:
        reply = await self._complete(http, question)
        return trim_reply(reply) if reply else FALLBACK_REPLY

    async def welcome(self, http: aiohttp.ClientSession, mention: str, display_name: str) -> str:
        prompt = (
            f"Souhaite la bienvenue à {display_name} qui vient d'arriver sur Mingati. "
            "Une seule phrase, drôle et un peu stressée."
        )
        reply = await self._complete(http, prompt)
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
        text = await self._complete(http, JOKE_PROMPT)
        if text and "\n" in text:
            setup, punchline = text.split("\n", 1)
            return Joke(setup.strip(), punchline.strip())
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
