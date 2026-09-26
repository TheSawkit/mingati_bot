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
│   └── voice.py       événements vocaux + /vocal
├── services/
│   └── voice_rooms.py VoiceRoomService (cycle de vie, contrôles) + VoiceRoomStore (SQLite)
├── interactions.py    erreurs communes slash/boutons/modals, MingatiView, MingatiModal
├── providers/         APIs externes : jeux gratuits, IA, serveurs (phase 4+)
├── views/
│   └── voice.py       panneau persistant, modals, sélecteurs
└── utils/
    ├── logging.py     configuration des logs + mémoire de la dernière erreur
    └── permissions.py check staff
```

## Responsabilités

| Couche | Rôle | Dépend de |
|---|---|---|
| `__main__` | Assemble les pièces et gère le cycle de vie | tout |
| `bot.py` | Bootstrap uniquement | config, database, cogs |
| `cogs/` | Traduit une interaction Discord en appel de service, formate la réponse | services, views |
| `services/` | Règles métier, testables sans Discord | database, providers |
| `providers/` | Parle aux APIs externes (HTTP avec timeout), normalise les données | aiohttp |
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
- Pragmas : `foreign_keys = ON`, `journal_mode = WAL`, `busy_timeout = 5000`.
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

## Flux des features à venir

- Qui joue ? — phase 3
- Jeux gratuits — phase 4
- Billy — phase 5
