import random

from mingati.errors import UserFacingError
from mingati.utils.text import clean_text

EIGHT_BALL_ANSWERS = (
    "Oui, clairement.",
    "C'est certain.",
    "Sans aucun doute.",
    "Probablement.",
    "Les signes disent oui.",
    "Réessaie plus tard...",
    "Je préfère ne pas te le dire maintenant.",
    "Concentre-toi et redemande.",
    "N'y compte pas.",
    "Ma réponse est non.",
    "Très peu probable.",
    "Euh... non. Enfin je crois.",
)
ROULETTE_CHAMBERS = 6
MAX_DICE = 10
MAX_FACES = 1000


def roll_dice(faces: int, count: int, rng: random.Random) -> list[int]:
    if not 2 <= faces <= MAX_FACES or not 1 <= count <= MAX_DICE:
        raise UserFacingError(f"Entre 1 et {MAX_DICE} dés de 2 à {MAX_FACES} faces.")
    return [rng.randint(1, faces) for _ in range(count)]


def flip_coin(rng: random.Random) -> str:
    return rng.choice(("Pile", "Face"))


def shake_eight_ball(rng: random.Random) -> str:
    return rng.choice(EIGHT_BALL_ANSWERS)


def pull_trigger(rng: random.Random) -> bool:
    """Russian roulette: True means the bullet was in the chamber (1 chance in 6)."""
    return rng.randrange(ROULETTE_CHAMBERS) == 0


def split_choices(raw: str) -> list[str]:
    """'Valorant, LoL ; valorant' → ['Valorant', 'LoL']: non-empty, case-insensitive unique."""
    unique: dict[str, str] = {}
    for part in raw.replace(";", ",").split(","):
        option = clean_text(part)
        if option:
            unique.setdefault(option.casefold(), option)
    return list(unique.values())


def pick_game(raw_choices: str, rng: random.Random) -> str:
    choices = split_choices(raw_choices)
    if len(choices) < 2:
        raise UserFacingError("Donne au moins deux jeux séparés par des virgules.")
    return rng.choice(choices)
