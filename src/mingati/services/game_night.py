import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from mingati.errors import UserFacingError
from mingati.services.gaming_sessions import MAX_PLAYERS, MIN_PLAYERS, parse_clock
from mingati.utils.text import clean_text

DATE_PATTERN = re.compile(r"^(?P<day>\d{1,2})/(?P<month>\d{1,2})(?:/(?P<year>\d{4}))?$")
MIN_NOTICE = timedelta(minutes=10)
MAX_AHEAD = timedelta(days=60)
DEFAULT_DURATION = timedelta(hours=3)
MAX_DESCRIPTION_LENGTH = 500


@dataclass(frozen=True, slots=True)
class GameNight:
    game: str
    starts_at: datetime
    ends_at: datetime
    players: int
    description: str | None
    host_name: str

    @property
    def event_name(self) -> str:
        return f"🎮 Game night : {self.game}"[:100]

    @property
    def event_description(self) -> str:
        """Text of the native Discord event, which has no player cap of its own."""
        lines = [f"👥 {self.players} joueurs · organisé par {self.host_name}"]
        if self.description:
            lines.append(self.description)
        lines.append("Clique sur « Intéressé » pour être prévenu au lancement.")
        return "\n\n".join(lines)


def parse_day(raw: str, today: date) -> date:
    """'aujourd'hui', 'demain', 'JJ/MM' (next occurrence) or 'JJ/MM/AAAA'."""
    text = raw.strip().lower()
    if text in ("aujourd'hui", "aujourdhui", "ce soir"):
        return today
    if text == "demain":
        return today + timedelta(days=1)
    match = DATE_PATTERN.match(text)
    if match is None:
        raise UserFacingError("Date invalide. Exemples : `demain`, `27/09`, `27/09/2026`.")
    try:
        day = date(int(match["year"] or today.year), int(match["month"]), int(match["day"]))
    except ValueError as error:
        raise UserFacingError("Cette date n'existe pas.") from error
    if match["year"] is None and day < today:
        day = day.replace(year=today.year + 1)
    return day


def plan_game_night(
    *,
    game: str,
    day: str,
    time: str,
    players: int,
    description: str | None,
    host_name: str,
    now: datetime,
) -> GameNight:
    """Validate /game-night input and compute its time window in now's timezone."""
    game = clean_text(game)
    if not game:
        raise UserFacingError("Indique le jeu.")
    if not MIN_PLAYERS <= players <= MAX_PLAYERS:
        raise UserFacingError(
            f"Le nombre de joueurs doit être entre {MIN_PLAYERS} et {MAX_PLAYERS}."
        )
    hour, minute = parse_clock(time)
    start = datetime.combine(parse_day(day, now.date()), datetime.min.time(), now.tzinfo).replace(
        hour=hour, minute=minute
    )
    if start < now + MIN_NOTICE:
        raise UserFacingError("La game night doit commencer dans au moins 10 minutes.")
    if start > now + MAX_AHEAD:
        raise UserFacingError("Pas plus de 60 jours à l'avance.")
    details = clean_text(description)[:MAX_DESCRIPTION_LENGTH] or None
    return GameNight(game, start, start + DEFAULT_DURATION, players, details, host_name)
