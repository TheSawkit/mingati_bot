# Mingati Bot

[![CI](https://github.com/TheSawkit/mingati_bot/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/TheSawkit/mingati_bot/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![discord.py](https://img.shields.io/badge/discord.py-2.7-5865F2)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Le bot Discord du serveur de potes **Mingati !** : il crée des salons vocaux à la demande, aide à trouver des coéquipiers, annonce les jeux gratuits et héberge Billy, le souffre-douleur à répartie.

Pensé pour un petit serveur (~20 personnes), il tourne 24 h/24 sur un simple Raspberry Pi, sans aucun service payant.

---

## Ce que fait le bot

### 🔊 Des salons vocaux qui apparaissent et disparaissent tout seuls

Tu rejoins le salon **« ➕・CRÉER UN VOCAL »** → le bot te crée ton propre salon (« *Pseudo's Palace* ») et t'y déplace. Un panneau de boutons te permet de le renommer, le verrouiller, inviter quelqu'un, limiter les places ou le donner à un ami. Quand tout le monde est parti, le salon s'efface.

### 🎮 « Qui joue ? »

`/jouer` publie une carte du genre :

```text
🎮 Cyberpunk 2077
🖥️ PC
🕘 21:00 (dans 1 heure)
👥 2 / 4
@Alice 👑
@Bob
[ Je rejoins ] [ Je quitte ] [ 🎙 Créer le vocal ]
```

Les autres cliquent pour rejoindre, et un bouton ouvre un vocal réservé aux joueurs inscrits. La carte disparaît d'elle-même quand la partie est passée.

### 🎁 Les jeux gratuits, sans chercher

Le bot surveille **Epic Games, Steam et GOG** et poste chaque nouveau jeu offert, avec son image et sa date de fin. Chaque jeu n'est annoncé qu'une seule fois.

### 🎬 Films et séries

`/watch film:NomDuFilm` recherche directement un film ou une série, puis permet de choisir le résultat, consulter la fiche TMDB, naviguer dans la saga ou les saisons/épisodes, et voir les disponibilités de visionnage en Belgique.

### 🤖 Billy, le souffre-douleur

Billy est anxieux et maladroit… mais il a de la répartie. Insulte-le avec `/billy`, il te renvoie la vanne en te visant par ton pseudo. Il peut aussi raconter une blague (`/blague`) et souhaiter la bienvenue aux nouveaux.

> Vannes de potes uniquement : Billy ne fait jamais de remarque raciste, sexiste, homophobe, ni sur le handicap, la famille ou la santé.

### Et aussi

| Commande | Ce que ça fait |
|---|---|
| `/mingati` | Un panneau permanent « Qu'est-ce qu'on fait ? » avec des boutons vers tout le reste |
| `/game-night` | Programme une soirée jeu comme un vrai événement Discord (les intéressés sont prévenus) |
| `/dé` `/coinflip` `/8ball` `/roulette` `/random-game` | Petits jeux : lancer de dés, pile ou face, boule magique, roulette russe, tirage au sort du jeu du soir |
| `/server status` | Est-ce que notre serveur Minecraft est en ligne ? Combien de joueurs ? |
| `/en-jeu` | Qui joue à quoi en ce moment (option à activer) |
| `/watch` | Recherche un film ou une série, affiche ses infos TMDB et les services de visionnage référencés pour la Belgique |

La liste complète des commandes est dans le [guide d'installation](docs/INSTALLATION.md#8-les-commandes).

## Ce que le bot ne fait pas

- **Il ne lit pas vos messages.** Il ne réagit qu'aux commandes `/` et, si l'option est activée, aux messages qui mentionnent Billy.
- **Il n'a pas les droits d'administrateur.** Il ne demande que les permissions dont chaque fonction a besoin.
- **Pas de points, pas de niveaux, pas de pub.** Juste des outils pour jouer ensemble.

---

## Installer ton propre Mingati Bot

Tout est expliqué pas à pas, même sans être développeur, dans **[docs/INSTALLATION.md](docs/INSTALLATION.md)** : créer le bot sur Discord, choisir les permissions, remplir la configuration, le lancer sur un Raspberry Pi.

En résumé, avec [Docker](https://docs.docker.com/engine/install/) installé :

```bash
git clone https://github.com/TheSawkit/mingati_bot.git
cd mingati_bot
cp .env.example .env
mkdir -p data
docker compose up -d --build
```

Il faut ensuite remplir `.env` (token Discord, IDs des salons…) : c'est la partie détaillée dans le guide.

## Pour les développeurs

| | |
|---|---|
| Langage | Python 3.12, [uv](https://docs.astral.sh/uv/) |
| Discord | discord.py 2.7 (slash commands, boutons, modals) |
| Données | SQLite (aiosqlite), migrations SQL versionnées |
| IA | Tout fournisseur au format OpenAI : Groq par défaut, Gemini possible |
| Qualité | Ruff, pytest, CI GitHub Actions (tests + image Docker amd64/arm64) |

```bash
uv sync            # installe Python 3.12 et les dépendances exactes
uv run pytest      # lance les tests
uv run mingati     # lance le bot (avec un .env rempli)
```

```text
src/mingati/
├── bot.py         démarrage et branchement des modules
├── cogs/          commandes et événements Discord
├── services/      règles métier, testables sans Discord
├── providers/     APIs externes (boutiques, IA, blagues, serveurs de jeux)
├── views/         boutons, menus, fenêtres
└── migrations/    schéma SQLite
```

- **[CONTRIBUTING.md](CONTRIBUTING.md)** : installer l'environnement, règles du projet, recettes pas à pas pour ajouter une commande, une source de jeux gratuits, un jeu serveur…
- **[ARCHITECTURE.md](ARCHITECTURE.md)** : comment le bot est construit et pourquoi.

## Licence

[MIT](LICENSE) : tu peux réutiliser, modifier et redistribuer ce code, en gardant la mention de copyright.
