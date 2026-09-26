# Mingati Bot

Bot Discord privé du serveur **Mingati !** (~20 potes). Petit, fiable, pensé pour tourner 24/7 sur un Raspberry Pi.

> **V2 en cours de reconstruction.** Phases 1 (fondations) et 2 (vocaux temporaires) terminées. Les fonctionnalités arrivent phase par phase — voir [Roadmap](#roadmap).

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Stack](#stack)
- [Discord Developer Portal](#discord-developer-portal)
- [Configuration](#configuration)
- [Lancement local](#lancement-local)
- [Docker](#docker)
- [Raspberry Pi](#raspberry-pi)
- [Tests et qualité](#tests-et-qualité)
- [Dépannage](#dépannage)
- [Roadmap](#roadmap)

## Fonctionnalités

| Commande | Qui | Description |
|---|---|---|
| `/bot status` | Staff | Uptime, latence, version, état SQLite, dernière erreur |
| `/vocal rename` `lock` `unlock` `invite` `limit` `transfer` `close` | Propriétaire du vocal | Contrôle de son vocal temporaire |

### Vocaux temporaires

- Rejoindre **➕・CRÉER UN VOCAL** (communauté) ou **🎮・CRÉER UN VOCAL** (gaming) crée un vocal « *Pseudo's Palace* » dans la même catégorie et t'y déplace.
- Un panneau de contrôle (Renommer, Limite, Inviter, Verrouiller, Déverrouiller, Transférer, Fermer) est posté dans le chat du vocal. Les mêmes actions existent en `/vocal`.
- Le vocal est supprimé dès qu'il ne reste plus d'humain dedans.
- Si le propriétaire part, un membre encore présent devient propriétaire au hasard.
- Un membre ne possède qu'un vocal à la fois : revenir dans le salon déclencheur le renvoie dans le sien.
- Au démarrage, le bot répare l'état : salons disparus oubliés, salons vides supprimés, propriétaires absents remplacés, membres en attente dans un déclencheur servis.
- Le bot ne supprime **jamais** un salon qu'il n'a pas créé (suivi par ID en base, pas par nom).

Toutes les commandes sont des **slash commands** synchronisées sur le serveur Mingati au démarrage. Il n'y a plus de commandes `!prefix`.

## Stack

| Élément | Choix |
|---|---|
| Langage | Python 3.12 |
| Discord | discord.py 2.7 |
| HTTP | aiohttp |
| Stockage | SQLite via aiosqlite, migrations versionnées |
| Configuration | pydantic-settings (variables d'environnement / `.env`) |
| Outillage | uv, Ruff, pytest, pytest-asyncio |
| Déploiement | Docker Compose (amd64 + arm64) |

L'architecture est décrite dans [ARCHITECTURE.md](ARCHITECTURE.md).

## Discord Developer Portal

1. Créer une application sur <https://discord.com/developers/applications>.
2. Onglet **Bot** → *Reset Token* → copier le token dans `DISCORD_TOKEN`.
3. Onglet **Bot** → *Privileged Gateway Intents* : **tout laisser désactivé**. Le bot n'en a pas besoin par défaut (voir [Intents](#intents)).
4. Onglet **OAuth2 → URL Generator** : scopes `bot` et `applications.commands`, puis cocher les permissions ci-dessous.
5. Ouvrir l'URL générée et inviter le bot sur Mingati.

### Permissions

Principe du moindre privilège : **jamais `Administrator`**.

| Permission | Pourquoi |
|---|---|
| View Channels | Voir les salons où il agit |
| Send Messages | Publier cartes, free games, réponses |
| Embed Links | Messages en embeds |
| Read Message History | Mettre à jour ses propres messages (hub, cartes) |
| Manage Channels | Créer, renommer, supprimer les vocaux temporaires |
| Manage Roles | Modifier les permissions d'un vocal : verrouiller, déverrouiller, inviter |
| Connect | Obligatoire pour déplacer un membre dans un vocal |
| Move Members | Déplacer le membre dans son vocal |

Sources : [Modify Channel / Edit Channel Permissions](https://discord.com/developers/docs/resources/channel) exigent `MANAGE_ROLES` pour toucher aux permissions d'un salon ; [Modify Guild Member](https://discord.com/developers/docs/resources/guild#modify-guild-member) exige `MOVE_MEMBERS` + `CONNECT` sur le salon cible.

**Important — rôle du bot en bas de la hiérarchie.** `Manage Roles` permet d'attribuer les rôles situés *sous* celui du bot. Dans *Paramètres du serveur → Rôles*, place le rôle du bot tout en bas : il ne pourra attribuer aucun rôle, mais pourra toujours gérer les permissions de ses vocaux. Les membres ne reçoivent eux **aucune** permission de gestion : tout passe par le bot.

Sans `Manage Roles`, les vocaux sont quand même créés et supprimés ; seuls verrouiller, déverrouiller et inviter répondent « il me manque des permissions ».

### Intents

| Intent | Activé | Condition |
|---|---|---|
| Guilds | Oui | Toujours |
| Voice States | Oui | Vocaux temporaires (non privilégié) |
| Message Content | Non | Uniquement si le mode `@Billy` est activé (phase 5) |
| Server Members | Non | Uniquement si réellement nécessaire |
| Presence | Non | Uniquement si la feature présence est activée (phase 9) |

## Configuration

```bash
cp .env.example .env
```

Puis remplir `.env`. Le fichier n'est **jamais** commité.

| Variable | Obligatoire | Description |
|---|---|---|
| `DISCORD_TOKEN` | Oui | Token du bot |
| `DISCORD_GUILD_ID` | Oui | ID du serveur Mingati (les commandes y sont synchronisées) |
| `CHANNEL_CHAT_ID` | Non | Salon de discussion général |
| `CHANNEL_GAMING_ID` | Non | Salon gaming |
| `CHANNEL_WHO_PLAYS_ID` | Non | Salon `qui-joue` |
| `CHANNEL_FREE_GAMES_ID` | Non | Salon des jeux gratuits |
| `CHANNEL_CREATE_VOICE_GENERAL_ID` | Non | Salon déclencheur « Créer un vocal » communauté |
| `CHANNEL_CREATE_VOICE_GAMING_ID` | Non | Salon déclencheur « Créer un vocal » gaming |
| `ROLE_STAFF_ID` | Non | Rôle autorisé aux commandes staff |
| `ROLE_MODERATOR_ID` | Non | Second rôle autorisé aux commandes staff |
| `LLM_PROVIDER` | Non | Fournisseur IA (`gemini`) |
| `LLM_MODEL` | Non | Modèle IA, jamais codé en dur |
| `GEMINI_API_KEY` | Non | Clé API Gemini |
| `DATABASE_PATH` | Non | Chemin SQLite, défaut `data/mingati.db` |
| `LOG_LEVEL` | Non | `DEBUG`, `INFO` (défaut), `WARNING`, `ERROR` |

Une variable vide est traitée comme non définie. Pour récupérer un ID Discord : *Paramètres → Avancés → Mode développeur*, puis clic droit → *Copier l'identifiant*.

Pour un environnement de dev, utiliser un **serveur Discord de test** et un second bot, avec son propre `.env`.

## Lancement local

Prérequis : [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run mingati
```

`uv sync` installe Python 3.12 si besoin, les dépendances exactes de `uv.lock` et le bot en mode éditable.

## Docker

```bash
mkdir -p data
docker compose up -d --build
```

- Image `python:3.12-slim`, multi-stage, utilisateur non-root (UID 1000).
- La base SQLite vit dans `./data` (monté sur `/app/data`) et survit aux rebuilds.
- Les secrets viennent de `.env`, jamais copié dans l'image.
- Logs Docker plafonnés à 3 × 10 Mo (carte SD friendly).

## Raspberry Pi

Image construite pour ARM64 en CI ; cible : Raspberry Pi OS 64 bits (Pi 4 / Pi 5). Installer Docker via le script officiel : <https://docs.docker.com/engine/install/debian/>.

| Action | Commande |
|---|---|
| Premier lancement | `mkdir -p data && docker compose up -d --build` |
| Logs | `docker compose logs -f` |
| Redémarrer | `docker compose restart` |
| Mettre à jour | `git pull && docker compose up -d --build` |
| Arrêter | `docker compose down` |
| Sauvegarder la base | `cp data/mingati.db data/mingati.db.bak` (bot arrêté) |

## Tests et qualité

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

La CI GitHub Actions lance ces trois étapes puis construit l'image Docker pour `amd64` et `arm64`. Elle ne sert **pas** à héberger le bot.

## Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `Invalid configuration, check your .env file` | Variable obligatoire absente ou ID non numérique | Comparer `.env` avec `.env.example` |
| `Discord rejected DISCORD_TOKEN` | Token révoqué ou mal copié | Régénérer le token dans le Developer Portal |
| `A privileged intent is enabled in code...` | Feature optionnelle activée sans l'intent côté portail | Activer l'intent dans *Bot → Privileged Gateway Intents* |
| `Bot is not a member of guild ...` | Mauvais `DISCORD_GUILD_ID` ou bot pas invité | Vérifier l'ID, réinviter le bot |
| Slash commands absentes | Scope `applications.commands` manquant | Réinviter le bot avec les deux scopes |
| `PermissionError` sur `data/` dans Docker | `./data` créé par root | `sudo chown -R 1000:1000 data` |
| `unable to open database file` | Dossier `data/` absent ou non monté | `mkdir -p data`, vérifier `compose.yaml` |
| Rien ne se passe en rejoignant « Créer un vocal » | ID du salon déclencheur absent ou faux | Vérifier `CHANNEL_CREATE_VOICE_*_ID` ; le log de démarrage signale un déclencheur introuvable |
| « Il me manque des permissions Discord » sur verrouiller / inviter | `Manage Roles` absent | Donner `Manage Roles` au rôle du bot (placé en bas de la hiérarchie) |
| Vocal créé mais membre pas déplacé | `Move Members` ou `Connect` absent sur la catégorie | Vérifier les permissions du rôle du bot sur la catégorie |
| Renommage qui échoue | Discord limite fortement les renommages de salon | Attendre quelques minutes |
| Warning `PyNaCl is not installed` | Normal : le bot ne joue pas d'audio | Rien à faire |
| Bot ne redémarre pas après reboot du Pi | Service Docker non activé | `sudo systemctl enable docker` |

## Roadmap

| Phase | Contenu | État |
|---|---|---|
| 1 | Fondations : config, logging, SQLite + migrations, Docker, CI, `/bot status` | Terminé |
| 2 | Vocaux temporaires | Terminé |
| 3 | Qui joue ? (`/jouer`) | À faire |
| 4 | Jeux gratuits Steam / Epic / GOG | À faire |
| 5 | Billy (IA) + `/blague` | À faire |
| 6 | Hub `/mingati` | À faire |
| 7 | Game night + commandes fun | À faire |
| 8 | Serveurs de jeux (Minecraft) | À faire |
| 9 | Optionnel (présence…) | À valider |
