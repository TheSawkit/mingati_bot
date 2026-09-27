# Contribuer à Mingati Bot

Ce guide explique comment travailler sur le code : installer l'environnement, respecter les règles du projet, et ajouter une fonctionnalité sans casser le reste. Pour comprendre *comment* le bot est construit, lis [ARCHITECTURE.md](ARCHITECTURE.md). Pour l'héberger, [docs/INSTALLATION.md](docs/INSTALLATION.md).

**Sommaire**

- [Installer l'environnement](#installer-lenvironnement)
- [Tester sur un vrai Discord](#tester-sur-un-vrai-discord)
- [Les règles du projet](#les-règles-du-projet)
- [Recettes](#recettes)
- [Tests](#tests)
- [Git et pull requests](#git-et-pull-requests)

---

## Installer l'environnement

Prérequis : [uv](https://docs.astral.sh/uv/getting-started/installation/). uv installe lui-même Python 3.12 et les versions exactes des dépendances figées dans `uv.lock`.

```bash
git clone https://github.com/TheSawkit/mingati_bot.git
cd mingati_bot
uv sync
uv run pytest
```

Si les tests passent, tout est prêt. Les commandes du quotidien :

| Commande | Rôle |
|---|---|
| `uv run pytest` | Tous les tests (moins de 2 s) |
| `uv run pytest tests/test_voice_rooms.py -k lock` | Un fichier, ou les tests dont le nom contient `lock` |
| `uv run ruff check .` | Linter |
| `uv run ruff format .` | Formatage automatique |
| `uv run mingati` | Lancer le bot (lit `.env`) |

Ce sont exactement les étapes de la CI (`.github/workflows/ci.yml`), qui construit en plus l'image Docker pour amd64 et arm64 (Raspberry Pi).

## Tester sur un vrai Discord

Ne développe jamais avec le bot de production. Crée **un serveur Discord de test** et **une seconde application** dans le [Developer Portal](https://discord.com/developers/applications), puis un `.env` local qui pointe vers eux (voir [docs/INSTALLATION.md](docs/INSTALLATION.md#5-remplir-la-configuration)).

Les slash commands sont synchronisées sur le serveur `DISCORD_GUILD_ID` à chaque démarrage : une nouvelle commande apparaît immédiatement, sans attendre la propagation mondiale de Discord (jusqu'à une heure).

## Les règles du projet

### Les couches

Chaque dossier a un rôle, et une couche n'importe que celles situées en dessous d'elle :

```text
cogs/      Discord : commandes, boutons, événements. Fins : ils traduisent et délèguent.
  ↓
views/     Composants Discord (embeds, boutons, modals). Aucune règle métier.
  ↓
services/  Règles métier. Testables sans Discord, sans réseau.
  ↓
providers/ APIs externes (HTTP avec timeout). Normalisent les réponses.
database.py  Accès SQLite.
```

`bot.py` ne fait que brancher les pièces. Si tu écris un `if` qui décide d'une règle (« un membre ne peut avoir qu'un vocal »), il va dans un service, pas dans un cog.

### Le code

| Règle | Pourquoi |
|---|---|
| **Zéro commentaire en ligne** | Le nom des fonctions et des variables doit suffire. Si un commentaire semble nécessaire, renomme |
| **Docstring d'une ligne sur le public uniquement** | Ce que fait la fonction et pourquoi, jamais comment. Pas de docstring sur les fonctions `_privées` |
| **Type hints partout** | Le code se lit sans deviner les types |
| **Aucune valeur magique** | Toute limite (`MAX_USER_LIMIT`, `USER_COOLDOWN`…) est une constante nommée en haut du module |
| **Aucun ID Discord en dur** | Tout vient de `Settings` (`src/mingati/config.py`) |
| **Erreurs pour l'utilisateur : `UserFacingError`** | Son message est affiché tel quel, en éphémère. Toute autre exception est loggée et l'utilisateur reçoit un message générique (`src/mingati/interactions.py`) |
| **Jamais de code bloquant** | Tout est `async` ; tout appel réseau passe par `providers/http.py` (timeout 20 s, retries sur 5xx) |
| **Moindre privilège** | Une nouvelle permission ou un nouvel intent se justifie dans la doc, et une option qui demande un intent privilégié est désactivée par défaut |
| **Pas d'exception avalée en silence** | Un `except` logge ou relève, toujours |

Ruff (lint + format, lignes de 100 caractères) doit passer sans avertissement.

## Recettes

Chaque recette liste les fichiers à toucher et le test qui prouve que ça marche.

### Ajouter une slash command

1. Crée `src/mingati/cogs/ma_feature.py` avec un cog et une fonction `setup` :

   ```python
   from __future__ import annotations

   import discord
   from discord import app_commands
   from discord.ext import commands

   from mingati.bot import MingatiBot


   class MaFeature(commands.Cog):
       def __init__(self, bot: MingatiBot) -> None:
           self.bot = bot

       @app_commands.command(name="salut", description="Dit bonjour")
       @app_commands.guild_only()
       async def salut(self, interaction: discord.Interaction) -> None:
           await interaction.response.send_message(f"Salut {interaction.user.mention} !")


   async def setup(bot: MingatiBot) -> None:
       await bot.add_cog(MaFeature(bot))
   ```

2. Ajoute `"mingati.cogs.ma_feature"` au tuple `EXTENSIONS` de `src/mingati/bot.py`.
3. Ajoute la commande au dictionnaire attendu dans `test_cogs_register_expected_commands_and_persistent_views` (`tests/test_bot.py`). Ce test échoue tant que la commande n'est pas enregistrée.
4. Si la commande est réservée au staff, ajoute `@staff_only()` (`src/mingati/utils/permissions.py`).
5. Si elle contient une règle métier, mets-la dans un service et teste-la dans `tests/`.

Si la commande a des **boutons qui doivent survivre à un redémarrage**, crée une vue dans `views/` qui hérite de `MingatiView`, avec `timeout=None` et des `custom_id` fixes (`mingati:ma_feature:action`), enregistrée avec `self.bot.add_view(...)` dans `cog_load`. Pense à mettre à jour le nombre de vues persistantes attendu dans le même test.

### Ajouter une table (migration)

1. Crée `src/mingati/migrations/NNNN_description.sql` avec le numéro suivant, sans trou (`0006_…` après `0005_…`).
2. Écris uniquement du SQL ; la migration s'exécute dans une transaction au démarrage, et la version est suivie par `PRAGMA user_version`.
3. Ne modifie **jamais** une migration déjà publiée : ajoute-en une nouvelle.
4. `test_every_packaged_migration_is_applied` (`tests/test_database.py`) vérifie que toutes les migrations s'appliquent.

### Ajouter une source de jeux gratuits

1. Crée `src/mingati/providers/games/ma_boutique.py` :
   - une fonction **pure** `parse_ma_boutique(payload) -> list[FreeGame]`, qui lève `ProviderError` si la réponse n'a pas la forme attendue ;
   - une classe avec `name`, `label` et `async def fetch(self, http) -> list[FreeGame]`, qui appelle `fetch_json` puis le parseur.
2. Ajoute-la à `default_game_providers()` (`src/mingati/providers/games/__init__.py`).
3. Enregistre une **vraie réponse** de l'API, réduite à quelques éléments, dans `tests/data/`, et teste le parseur dessus (modèle : `tests/test_game_providers.py`).

La déduplication, la validation, la publication et le premier passage silencieux sont gérés par `FreeGameService` : rien à refaire.

### Ajouter un jeu à `/server status`

1. Crée `src/mingati/providers/servers/mon_jeu.py` : une classe avec `kind`, `label`, `default_port` et `async def status(self, address) -> ServerStatus`. Un serveur injoignable renvoie `OFFLINE`, il ne lève pas d'erreur.
2. Ajoute-la à `default_server_providers()` (`src/mingati/providers/servers/__init__.py`). Elle apparaît automatiquement dans l'autocomplétion de `/server add`.
3. Teste le cas injoignable (modèle : `test_unreachable_minecraft_server_is_offline` dans `tests/test_servers.py`).

### Ajouter un fournisseur IA

Si le fournisseur parle le format OpenAI *chat completions*, c'est de la configuration :

1. `src/mingati/config.py` : ajoute la valeur au `Literal` de `llm_provider` et un champ `mon_fournisseur_api_key: SecretStr | None = None`.
2. `src/mingati/providers/ai/__init__.py` : ajoute son URL à `BASE_URLS` et sa clé au dictionnaire de `create_ai_provider`.
3. `.env.example` et la doc : la nouvelle variable.
4. Complète `test_ai_provider_follows_llm_provider_setting` (`tests/test_billy.py`).

### Ajouter une option désactivable

Pour une fonction qui demande un intent privilégié (modèle : la présence, `PRESENCE_ENABLED`) :

1. Un booléen `False` par défaut dans `Settings`.
2. L'intent correspondant dans `build_intents(settings)` (`src/mingati/bot.py`), activé seulement si l'option l'est.
3. Le cog n'est ajouté (ou le listener enregistré) que si l'option est active.
4. Un test par état : intents (`tests/test_bot.py`) et commande présente ou absente (`tests/test_presence.py`).
5. La doc : tableau des intents et des options dans [docs/INSTALLATION.md](docs/INSTALLATION.md).

## Tests

Les tests n'appellent jamais Discord ni Internet.

| Outil | Où | Usage |
|---|---|---|
| Fixtures `database` et `open_database` | `tests/conftest.py` | Une vraie base SQLite temporaire, migrée, toujours fermée en fin de test |
| Doublures Discord (`FakeGuild`, `FakeMember`, `FakeVoiceChannel`…) | `tests/fakes.py` | Simulent juste ce que les services utilisent |
| Réponses d'API figées | `tests/data/` | Vraies réponses Epic, Steam, GOG, réduites |
| Isolation de l'environnement | `tests/conftest.py` | Toute variable de `Settings` présente sur ta machine est effacée pendant les tests |

Principes :

- **Un bug corrigé = un test qui échouait avant la correction.** Vérifie-le en retirant la correction.
- Les tirages aléatoires prennent un `random.Random` en paramètre, pour des tests déterministes (`services/fun.py`).
- L'heure courante est passée en paramètre (`now`) plutôt que lue dans le service.

## Git et pull requests

| Branche | Rôle |
|---|---|
| `main` | Ce qui tourne en production |
| `dev` | Intégration : la CI y tourne à chaque push |
| `feat/…`, `fix/…` | Ton travail, partant de `dev` |

Messages de commit au format [Conventional Commits](https://www.conventionalcommits.org/fr/) : `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`, `ci:`. Un commit = un changement logique ; plusieurs petits commits valent mieux qu'un gros.

Avant d'ouvrir une pull request vers `dev` :

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

- [ ] Les trois commandes passent
- [ ] Les nouvelles règles ont des tests
- [ ] La doc est à jour (README, INSTALLATION, ARCHITECTURE, `.env.example`)
- [ ] Aucun secret dans le code ni dans les commits
