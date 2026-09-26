# Architecture

## Principes

- **Petit et fiable** : un seul process, une base SQLite, zéro service externe obligatoire.
- **Couches séparées** : Discord ne touche jamais à SQLite directement, la logique métier ne connaît pas Discord quand c'est évitable.
- **Aucun ID en dur** : tout ID Discord vient de `Settings`.
- **Moindre privilège** : intents et permissions ajoutés feature par feature, jamais `Administrator`.

## Arborescence

```text
src/mingati/
├── __main__.py        entrée `mingati` : config → logging → DB → bot, arrêt propre sur SIGTERM
├── bot.py             MingatiBot : bootstrap, chargement des cogs, sync des slash commands, erreurs globales
├── config.py          Settings (pydantic-settings)
├── database.py        connexion SQLite partagée, transactions, migrations
├── errors.py          UserFacingError
├── migrations/        NNNN_nom.sql, appliqués dans l'ordre
├── cogs/              commandes et événements Discord (fins)
│   ├── core.py        /bot status
│   ├── voice.py       événements vocaux + /vocal
│   └── gaming.py      /jouer, boutons des cartes, expiration
├── services/
│   ├── voice_rooms.py     VoiceRoomService (cycle de vie, contrôles) + VoiceRoomStore (SQLite)
│   ├── gaming_sessions.py GamingSessionService + validation /jouer (fonctions pures)
│   ├── session_voice.py   règles « Créer le vocal » d'une session (inscrits seulement, réutilisation)
│   ├── free_games.py      pipeline jeux gratuits (validation, déduplication, publication)
│   ├── billy.py           personnalité, limites d'usage, secours pour chaque réponse
│   ├── guild_config.py    état clé/valeur par serveur (position du hub)
│   └── game_servers.py    serveurs suivis + statut en parallèle
├── providers/
│   ├── http.py            client aiohttp partagé : timeout, retries
│   ├── games/             EpicProvider, SteamProvider, GogProvider → FreeGame
│   ├── ai/                AIProvider + OpenAICompatibleProvider (Gemini, Groq…)
│   ├── jokes.py           blagues-api.fr
│   └── servers/           ServerProvider + MinecraftJavaProvider (mcstatus)
├── interactions.py    erreurs communes slash/boutons/modals, MingatiView, MingatiModal
├── views/
│   ├── voice.py       panneau persistant, modals, sélecteurs
│   └── gaming.py      carte de session + boutons persistants
└── utils/
    ├── logging.py     configuration des logs + mémoire de la dernière erreur
    └── permissions.py check staff
```

## Responsabilités

| Couche | Rôle | Dépend de |
|---|---|---|
| `__main__` | Assemble les pièces et gère le cycle de vie | tout |
| `bot.py` | Bootstrap : instancie les services partagés, charge les cogs | config, database, services, interactions |
| `cogs/` | Traduit une interaction Discord en appel de service, formate la réponse | services, views |
| `services/` | Règles métier, testables sans Discord | database |
| `views/` | Composants interactifs persistants | services |
| `database.py` | Accès SQLite | aiosqlite |

Règle de dépendance : une couche n'importe que les couches à sa droite dans ce tableau.

## Démarrage

```text
mingati
 ├─ Settings()                       échec → message clair, exit 1
 ├─ setup_logging(LOG_LEVEL)
 ├─ Database.connect()               crée data/, PRAGMA, migrations
 └─ MingatiBot.start()
     └─ setup_hook()
         ├─ load_extension(cogs…)
         └─ tree.sync(guild=DISCORD_GUILD_ID)   sync instantanée, serveur unique
```

SIGTERM (`docker stop`) ou SIGINT ferment le bot puis la base proprement.

## Base de données

- Une seule connexion `aiosqlite`, protégée par un `asyncio.Lock` : deux coroutines ne peuvent pas entrelacer leurs requêtes dans une même transaction.
- `Database.transaction()` pour plusieurs écritures atomiques (`BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK`).
- Pragmas : `foreign_keys = ON`, `journal_mode = WAL`, `synchronous = NORMAL` (sûr en WAL, moins d'écritures sur la carte SD — [doc SQLite](https://sqlite.org/pragma.html#pragma_synchronous)), `busy_timeout = 5000`.
- Migrations : fichiers `src/mingati/migrations/NNNN_nom.sql`, numérotés sans trou. La version appliquée est stockée dans `PRAGMA user_version`. Chaque migration tourne dans sa propre transaction : un échec laisse la base à la version précédente.
- Chaque feature ajoute ses tables dans sa propre migration, au moment où elle en a besoin.

## Gestion des erreurs

- `UserFacingError` : erreur attendue, son message est affiché tel quel à l'utilisateur (ephemeral).
- Erreurs Discord connues (rôle manquant, cooldown, permission bot manquante, `403 Forbidden`) : message français clair.
- Slash commands, boutons et modals passent tous par `interactions.report_error` : même comportement partout.
- Tout le reste : log `ERROR` avec traceback + message générique à l'utilisateur. La dernière erreur est visible via `/bot status`.

## Logging

- Format : `date niveau logger: message`, sur stdout (récupéré par Docker).
- Le logger `discord` ne descend jamais sous `INFO` : en `DEBUG` il loggerait des payloads gateway (contenu de messages).
- Les secrets sont des `SecretStr` : jamais affichés dans un `repr` ni dans les logs.

## Vocaux temporaires

### Table

`temporary_voice_channels` : `channel_id` (PK), `guild_id`, `owner_id`, `trigger_channel_id`, `panel_message_id`, `is_locked`, `created_at`. Index unique `(guild_id, owner_id)` : un vocal par membre, garanti par la base.

### Flux

```text
VOICE_STATE_UPDATE (member, before, after)
 ├─ before est un vocal suivi en base ?
 │   ├─ plus aucun humain  → suppression salon + ligne
 │   └─ le propriétaire part → successeur aléatoire parmi les présents, panneau mis à jour
 └─ after est un déclencheur (comparaison d'ID) ?
     ├─ le membre a déjà un vocal → il y est renvoyé
     └─ sinon → création dans la catégorie du déclencheur, insertion en base,
                déplacement du membre, panneau posté dans le chat du vocal
                (échec du déplacement → salon supprimé)
```

### Concurrence

Création, suppression et transferts passent par un unique `asyncio.Lock` du service. Plusieurs `VOICE_STATE_UPDATE` simultanés sont donc traités l'un après l'autre : le second voit le vocal déjà créé et renvoie le membre dedans. Pour ~20 personnes, un verrou global est plus simple et suffisant. Les renommages restent hors verrou : Discord peut les faire patienter plusieurs minutes, ce qui bloquerait sinon tout le monde. Au-delà de 10 s, le bot abandonne et prévient.

### Permissions

- À la création, le vocal reçoit une copie des permissions de la catégorie (sans `Manage Roles`, que seul un admin peut poser à la création) et le propriétaire est autorisé explicitement. Si Discord refuse la copie, le vocal est créé avec les valeurs par défaut.
- **Verrouiller** : `Connect` refusé à `@everyone` et à chaque rôle ayant une permission propre au salon (une autorisation de rôle l'emporterait sinon sur le refus `@everyone`), autorisé nommément au propriétaire et aux présents.
- **Déverrouiller** : chaque rôle retrouve la valeur `Connect` de la catégorie ; les autorisations nominatives restent.
- **Inviter** : autorisation `View Channel` + `Connect` pour la personne.
- Les calculs de permissions sont des fonctions pures (`locked_overwrites`, `unlocked_overwrites`, …), testées sans Discord.

### Panneau persistant

`VoiceControlView` utilise des `custom_id` fixes (`mingati:voice:*`) et est enregistrée au chargement du cog : les boutons marchent encore après un redémarrage. Le salon concerné est déduit du salon où l'on clique ; pour `/vocal`, c'est le vocal où se trouve l'utilisateur.

### Récupération au démarrage

`on_ready` appelle `VoiceRoomService.reconcile` : lignes sans salon supprimées, salons vides supprimés, propriétaires absents remplacés, membres présents dans un déclencheur servis. Seuls les salons présents en base sont touchés.

## Services partagés

`MingatiBot` instancie les services partagés (`voice_rooms`, `gaming_sessions`). Les cogs les utilisent sans se connaître : quand le cog gaming crée un vocal, il émet l'événement interne `voice_room_created`, et le cog vocal poste le panneau.

## Qui joue ?

### Tables

- `gaming_sessions` : jeu, plateforme, mode, `max_players`, `starts_at` / `expires_at` (epoch UTC), salon et message de la carte, vocal lié.
- `gaming_session_members` : clé primaire `(session_id, user_id)` → double inscription impossible ; `ON DELETE CASCADE`.
- Index sur `expires_at` (balayage d'expiration), `(guild_id, host_id)` et `user_id` (départ du serveur).

### Flux

```text
/jouer → plan_session (validation, parsing heure, fenêtre)   pur, testé
       → service.create (session + hôte, 1 session active par hôte)
       → carte postée → message_id enregistré (échec d'envoi → session supprimée)

Bouton → session retrouvée par message_id → join/leave en transaction → carte éditée
Tâche 1 min → sessions expirées supprimées → cartes supprimées
RAW_MEMBER_REMOVE (si intent Members) → retrait partout → cartes éditées/supprimées
GUILD_CHANNEL_DELETE → vocal détaché des sessions → cartes rafraîchies (plus de lien mort)
```

### Vocal de session

`VoiceRoomService.open_session_room` réutilise le vocal du membre s'il en a un, sinon en crée un dans la catégorie du déclencheur gaming, ouvert nommément aux inscrits (`discord.Object(id)` suffit, pas besoin de l'intent Members). Une tâche toutes les 5 minutes supprime les vocaux vides créés depuis plus de 10 minutes : un vocal jamais rejoint ne reçoit aucun événement de départ.

## Jeux gratuits

### Providers

Chaque provider (`GameProvider` : `name`, `label`, `fetch(http)`) appelle une source JSON et renvoie des `FreeGame` normalisés. Le parsing est une fonction pure testée sur de vraies réponses figées dans `tests/data/`.

| Provider | Source | Règle |
|---|---|---|
| Epic | `freeGamesPromotions` | promotion en cours à `discountPercentage == 0` et prix remisé nul |
| Steam | recherche `json=1&maxprice=free&specials=1&category1=998` puis `api/appdetails` | `type == game` et `discount_percent == 100` |
| GOG | `catalog.gog.com/v1/catalog?price=between:0,0&discounted=eq:true` | prix final 0 et prix de base > 0 |

`providers/http.fetch_json` : timeout total 20 s, 3 tentatives sur erreur réseau ou 5xx, échec immédiat sur 4xx. Un payload inattendu lève `ProviderError`.

### Pipeline

```text
refresh (toutes les 2 h ou /freegames refresh)
 ├─ providers en parallèle (gather) ; une erreur = statut de la source, pas d'arrêt
 ├─ validation (titre, https, pas déjà terminé)
 ├─ INSERT OR IGNORE sur offer_key = source:id:fin   → déduplication
 │    première réussite d'une source : insérées comme déjà publiées (silencieux)
 │    offres sans date de fin disparues de la source : supprimées (ré-annonçables)
 ├─ publication des offres non publiées ; échec d'envoi = retenté au passage suivant
 └─ purge des offres terminées depuis plus de 30 jours
```

### Tables

- `free_games` : offre normalisée, `offer_key` unique, `published_at`, `message_id`.
- `game_sources` : dernière réussite, nombre de jeux, dernière erreur par source.

## Billy

```text
/billy ou @Billy
 ├─ prepare_question : nettoyage, longueur ≤ 500, IA configurée, UsageLimiter (20 s / membre, 300 / jour)
 │    refus → message éphémère, avant toute réponse publique
 └─ answer : persona système + question → AIProvider.complete (≤ 200 tokens)
      erreur réseau/API → phrase de secours « dans le personnage »
```

- `AIProvider` est un Protocol ; `OpenAICompatibleProvider` couvre tous les fournisseurs au format OpenAI *chat completions*. `create_ai_provider` choisit l'URL et la clé selon `LLM_PROVIDER`, le modèle vient toujours de `LLM_MODEL`.
- Pas de mémoire : chaque question est indépendante (coût et vie privée).
- Intents calculés depuis la config (`build_intents(settings)`) : `guild_messages` seulement si les mentions sont activées, `members` seulement si la bienvenue l'est. Les listeners correspondants ne sont enregistrés que dans ce cas.

## Hub

`/mingati` (staff) publie un embed + `HubView` persistante (`mingati:hub:*`). La position du message est stockée dans `guild_config` (`hub_channel_id`, `hub_message_id`) : relancer la commande édite le message existant au lieu d'en créer un. Les boutons ne font que lire les services existants (`gaming_sessions.list_open`, `free_games.active`, `billy`) et répondent en éphémère.

## Game night et fun

- `/game-night` : `plan_game_night` (pur, testé) valide et calcule la fenêtre dans `TIMEZONE`, puis `guild.create_scheduled_event` (externe, 3 h). Pas de table : l'événement natif est la source de vérité, Discord gère inscriptions et notifications.
- `services/fun.py` : tirages purs prenant un `random.Random` (tests déterministes, `SystemRandom` en production).

## Serveurs de jeux

- Table `game_servers` : `(guild_id, name)` unique, `name` en `COLLATE NOCASE`, `kind` = clé du provider.
- `ServerProvider` (`kind`, `label`, `status(address)`) renvoie un `ServerStatus` ; un serveur injoignable (réseau, DNS, timeout) donne `OFFLINE` au lieu d'une erreur.
- `GameServerService.statuses` interroge tous les serveurs en parallèle (`asyncio.gather`).
- Ajouter un jeu : écrire un provider et l'ajouter à `default_server_providers()`.

## Présence

- `services/presence.py` : fonctions pures sur les `Member` du cache (`activity.type is ActivityType.playing`), regroupées par jeu. Aucune table.
- `PRESENCE_ENABLED` active `presences` **et** `members` : `MemberCacheFlags.from_intents` ne met en cache que les membres en vocal sans `members`.
- Le cog n'est ajouté que si l'option est active : `/en-jeu` n'existe pas sinon.
