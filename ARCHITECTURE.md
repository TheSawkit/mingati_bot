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
│   └── core.py        /bot status
├── services/          logique métier (phase 2+)
├── providers/         APIs externes : jeux gratuits, IA, serveurs (phase 4+)
├── views/             boutons, selects, modals (phase 2+)
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
- Erreurs Discord connues (rôle manquant, cooldown, permission bot manquante) : message français clair.
- Tout le reste : log `ERROR` avec traceback + message générique à l'utilisateur. La dernière erreur est visible via `/bot status`.

## Logging

- Format : `date niveau logger: message`, sur stdout (récupéré par Docker).
- Le logger `discord` ne descend jamais sous `INFO` : en `DEBUG` il loggerait des payloads gateway (contenu de messages).
- Les secrets sont des `SecretStr` : jamais affichés dans un `repr` ni dans les logs.

## Flux des features

Documentés au fil des phases :

- Vocaux temporaires — phase 2
- Qui joue ? — phase 3
- Jeux gratuits — phase 4
- Billy — phase 5
