# Installer et héberger Mingati Bot

Ce guide va de zéro à un bot qui tourne 24 h/24. Aucune connaissance en programmation n'est nécessaire, seulement savoir taper des commandes dans un terminal.

**Sommaire**

1. [Ce qu'il te faut](#1-ce-quil-te-faut)
2. [Créer le bot sur Discord](#2-créer-le-bot-sur-discord)
3. [Inviter le bot sur ton serveur](#3-inviter-le-bot-sur-ton-serveur)
4. [Récupérer les identifiants de salons](#4-récupérer-les-identifiants-de-salons)
5. [Remplir la configuration](#5-remplir-la-configuration)
6. [Lancer le bot](#6-lancer-le-bot)
7. [Premiers pas sur Discord](#7-premiers-pas-sur-discord)
8. [Les commandes](#8-les-commandes)
9. [Mettre à jour et sauvegarder](#9-mettre-à-jour-et-sauvegarder)
10. [Remplacer l'ancien bot (V1)](#10-remplacer-lancien-bot-v1)
11. [Dépannage](#11-dépannage)

---

## 1. Ce qu'il te faut

| Élément | Détail |
|---|---|
| Une machine allumée en permanence | Un **Raspberry Pi 3B+, 4 ou 5** avec au moins 1 Go de RAM et **Raspberry Pi OS 64 bits** (l'image du bot est construite pour ARM 64 bits). Un PC ou un serveur Linux marche aussi |
| Docker | Installation officielle : <https://docs.docker.com/engine/install/debian/> |
| Git | `sudo apt install git` |
| Un compte Discord | Avec les droits d'administration sur ton serveur |

Le bot consomme environ **60 à 100 Mo de mémoire** et presque rien en processeur : n'importe quel Pi récent suffit.

> **Pas de Pi ?** Google Cloud offre une machine `e2-micro` et 30 Go de disque standard dans 3 régions US ([détails](https://docs.cloud.google.com/free/docs/free-cloud-features)), mais **pas l'adresse IPv4 publique** : 0,005 $/heure, soit environ 3,65 $/mois, gratuite une heure par mois seulement ([tarifs réseau](https://cloud.google.com/vpc/network-pricing)). Elle est indispensable : Discord n'est pas joignable en IPv6. Compte donc environ 3,65 $/mois minimum. Le bot s'y installe exactement comme sur un Pi.

## 2. Créer le bot sur Discord

1. Va sur <https://discord.com/developers/applications> et clique **New Application**. Donne-lui un nom (par exemple « Billy »).
2. Onglet **Bot** → **Reset Token** → copie le token affiché. C'est le mot de passe du bot : ne le partage jamais. Il ira dans `DISCORD_TOKEN` à l'étape 5.
3. Onglet **Bot** → **Privileged Gateway Intents** : laisse **tout désactivé** pour l'instant. Certaines options facultatives en demandent un, voir le tableau ci-dessous.

### Intents (ce que Discord envoie au bot)

Un *intent* est une catégorie d'événements que Discord accepte d'envoyer au bot. Par défaut, le bot n'en demande que deux, non sensibles.

| Intent | Nécessaire quand | Sensible (« privilégié ») |
|---|---|---|
| Guilds, Voice States | Toujours | Non |
| Guild Messages | `BILLY_MENTIONS_ENABLED=true` | Non |
| Server Members | `WELCOME_ENABLED=true` ou `PRESENCE_ENABLED=true` | **Oui** : à cocher dans le portail |
| Presence | `PRESENCE_ENABLED=true` | **Oui** : à cocher dans le portail |
| Message Content | Jamais | — |

Si tu actives une option sans cocher l'intent correspondant, le bot refuse de démarrer avec le message `A privileged intent is enabled in code but not in the Developer Portal`.

## 3. Inviter le bot sur ton serveur

1. Onglet **OAuth2 → URL Generator**.
2. Coche les scopes **`bot`** et **`applications.commands`**.
3. Coche les permissions suivantes, et rien de plus (jamais `Administrator`) :

| Permission | Pourquoi |
|---|---|
| View Channels | Voir les salons où il agit |
| Send Messages | Publier les cartes, les jeux gratuits, les réponses |
| Embed Links | Envoyer des messages mis en forme |
| Read Message History | Mettre à jour ses propres messages (hub, cartes) |
| Manage Channels | Créer, renommer et supprimer les vocaux temporaires |
| Manage Roles | Verrouiller, déverrouiller un vocal et y inviter quelqu'un |
| Connect | Obligatoire pour pouvoir déplacer un membre dans un vocal |
| Move Members | Déplacer le membre dans son vocal |
| Create Events | Créer les soirées `/game-night` |

4. Ouvre l'URL générée en bas de page et choisis ton serveur.
5. **Important** : dans *Paramètres du serveur → Rôles*, fais glisser le rôle du bot **tout en bas** de la liste. `Manage Roles` permet d'attribuer les rôles situés *sous* celui du bot : placé en bas, il ne peut en attribuer aucun, mais peut toujours gérer les permissions de ses propres vocaux.

Sources : [Discord — Channel](https://discord.com/developers/docs/resources/channel) (`MANAGE_ROLES` pour modifier les permissions d'un salon), [Discord — Modify Guild Member](https://discord.com/developers/docs/resources/guild#modify-guild-member) (`MOVE_MEMBERS` + `CONNECT` pour déplacer quelqu'un).

## 4. Récupérer les identifiants de salons

Le bot reconnaît les salons par leur **identifiant** (un grand nombre), jamais par leur nom : tu peux renommer ou déplacer un salon sans rien casser.

1. Discord → *Paramètres utilisateur → Avancés* → active le **Mode développeur**.
2. Clic droit sur un salon, un rôle ou le serveur → **Copier l'identifiant**.

## 5. Remplir la configuration

Sur la machine qui héberge le bot :

```bash
git clone https://github.com/TheSawkit/mingati_bot.git
cd mingati_bot
cp .env.example .env
nano .env
```

Le fichier `.env` contient tes secrets : il n'est jamais envoyé sur GitHub ni copié dans l'image Docker. Une ligne vide après le `=` veut dire « non configuré ».

### Obligatoire

| Variable | Valeur |
|---|---|
| `DISCORD_TOKEN` | Le token de l'étape 2 |
| `DISCORD_GUILD_ID` | L'identifiant de ton serveur |

### Salons et rôles

| Variable | Sert à |
|---|---|
| `CHANNEL_CREATE_VOICE_GENERAL_ID` | Salon « ➕ Créer un vocal » (communauté) |
| `CHANNEL_CREATE_VOICE_GAMING_ID` | Salon « 🎮 Créer un vocal » (gaming), aussi utilisé pour les vocaux de `/jouer` |
| `CHANNEL_WHO_PLAYS_ID` | Où publier les cartes `/jouer` (sinon : le salon où la commande est tapée) |
| `CHANNEL_FREE_GAMES_ID` | Où annoncer les jeux gratuits (sans lui : pas d'annonces) |
| `CHANNEL_CHAT_ID` | Où Billy souhaite la bienvenue |
| `CHANNEL_GAMING_ID` | Réservé, pas encore utilisé |
| `ROLE_STAFF_ID`, `ROLE_MODERATOR_ID` | Rôles autorisés à utiliser les commandes « staff » |

### Billy (IA)

| Variable | Valeur |
|---|---|
| `LLM_PROVIDER` | `groq` (par défaut) ou `gemini` |
| `LLM_MODEL` | `qwen/qwen3.8-27b` pour Groq (par défaut), par exemple `gemini-3.8-flash` pour Gemini |
| `GROQ_API_KEY` | Clé gratuite sur <https://console.groq.com/keys> |
| `GEMINI_API_KEY` | Clé gratuite sur <https://aistudio.google.com/apikey> |
| `BLAGUES_API_TOKEN` | Token gratuit sur <https://www.blagues-api.fr> pour `/blague` |

| Fournisseur | Offre gratuite |
|---|---|
| Groq | 30 requêtes par minute, 1 000 par jour ([doc](https://console.groq.com/docs/rate-limits)) |
| Gemini | Quotas affichés dans AI Studio ([doc](https://ai.google.dev/gemini-api/docs/rate-limits)) |

Billy se limite lui-même à une question toutes les 20 s par membre et à 300 appels par jour pour tout le serveur : il reste dans le gratuit. Sans clé IA, `/billy` répond qu'il dort ; `/blague` et la bienvenue marchent quand même.

### Options (désactivées par défaut)

| Variable | Effet | Intent à cocher (étape 2) |
|---|---|---|
| `BILLY_MENTIONS_ENABLED=true` | Billy répond aussi quand on écrit `@Billy …` | Aucun |
| `WELCOME_ENABLED=true` | Message de bienvenue pour les nouveaux | Server Members |
| `PRESENCE_ENABLED=true` | Commande `/en-jeu` | Server Members + Presence |

### Réglages avancés

| Variable | Défaut | Sert à |
|---|---|---|
| `TIMEZONE` | `Europe/Brussels` | Lire les heures tapées (« 21h ») |
| `STORE_COUNTRY` | `BE` | Pays utilisé pour interroger les boutiques de jeux |
| `DATABASE_PATH` | `data/mingati.db` | Emplacement de la base de données |
| `LOG_LEVEL` | `INFO` | Niveau de détail des logs (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

## 6. Lancer le bot

```bash
mkdir -p data
docker compose up -d --build
```

- Le premier lancement construit l'image : compte quelques minutes sur un Pi.
- `-d` fait tourner le bot en arrière-plan. Il redémarre tout seul en cas de plantage.
- Pour qu'il redémarre aussi après une coupure de courant : `sudo systemctl enable docker`.

Vérifie que tout va bien :

```bash
docker compose logs -f
```

Tu dois voir `Synced … slash commands` puis `Connected as …`. `Ctrl+C` pour quitter l'affichage des logs (le bot continue de tourner).

## 7. Premiers pas sur Discord

1. **`/bot status`** (staff) : affiche d'un coup ce qui est configuré, ce qui manque et la dernière erreur éventuelle.
2. **`/mingati`** (staff) : dans le salon de ton choix, publie le panneau permanent « Qu'est-ce qu'on fait ? ».
3. **`/server add`** (staff) : ajoute le serveur Minecraft du groupe, par exemple `nom:Survie adresse:mc.exemple.fr`.
4. Rejoins le salon « Créer un vocal » pour tester la création de salon.

## 8. Les commandes

| Commande | Qui | Ce que ça fait |
|---|---|---|
| `/vocal rename` `lock` `unlock` `invite` `limit` `transfer` `close` | Propriétaire du vocal | Gérer son vocal temporaire (aussi disponible en boutons dans le salon) |
| `/jouer jeu plateforme joueurs [mode] [heure] [duree]` | Tout le monde | Chercher des joueurs. `heure` : `21h`, `21h30`, `21:30` ou `maintenant` |
| `/game-night jeu date heure joueurs [description]` | Tout le monde | Programmer une soirée (événement Discord). `date` : `aujourd'hui`, `demain`, `27/09`, `27/09/2026` |
| `/billy question` | Tout le monde | Parler à Billy |
| `/blague` | Tout le monde | Une blague, chute cachée en spoiler |
| `/dé [faces] [nombre]` | Tout le monde | Lancer des dés |
| `/coinflip` | Tout le monde | Pile ou face |
| `/8ball question` | Tout le monde | La boule magique répond |
| `/roulette [membre]` | Tout le monde | Roulette russe, 1 chance sur 6 |
| `/random-game choix:"Valorant, LoL, Minecraft"` | Tout le monde | Tire au sort le jeu du soir |
| `/server status [nom]` | Tout le monde | État des serveurs de jeux suivis |
| `/en-jeu` | Tout le monde | Qui joue à quoi (si `PRESENCE_ENABLED=true`) |
| `/mingati` | Staff | Publier ou mettre à jour le hub |
| `/freegames refresh` `status` | Staff | Vérifier les jeux gratuits maintenant, voir l'état des sources |
| `/server add` `remove` | Staff | Gérer la liste des serveurs suivis |
| `/bot status` | Staff | État technique du bot |

Bon à savoir :

- Un vocal temporaire s'efface quand il n'y a plus personne. Si son propriétaire part, un autre membre présent en hérite.
- Les jeux gratuits sont vérifiés toutes les 2 heures. Au tout premier passage, ceux déjà gratuits sont enregistrés **sans annonce**, pour ne pas inonder le salon.
- Les cartes `/jouer` disparaissent à la fin de la session (3 h par défaut).

## 9. Mettre à jour et sauvegarder

| Action | Commande |
|---|---|
| Voir les logs | `docker compose logs -f` |
| Redémarrer | `docker compose restart` |
| Mettre à jour | `git pull && docker compose up -d --build` |
| Arrêter | `docker compose down` |
| Sauvegarder la base | `docker compose stop && cp data/mingati.db data/mingati.db.bak && docker compose start` |

Toutes les données (vocaux, sessions, jeux déjà annoncés, serveurs suivis) tiennent dans le seul fichier `data/mingati.db`. C'est lui qu'il faut sauvegarder.

Astuce : sur un Pi, une clé USB ou un petit SSD est plus robuste qu'une carte SD sur la durée. Le bot limite déjà ses écritures (SQLite en mode WAL, logs plafonnés à 30 Mo).

## 10. Remplacer l'ancien bot (V1)

La V2 fait tout ce que faisait la V1, sauf la commande « @bot dis … » (le bot supprimait ton message pour le reposter à sa place), abandonnée volontairement. Pour retrouver le comportement de la V1, active `BILLY_MENTIONS_ENABLED=true` et `WELCOME_ENABLED=true` (et coche *Server Members* dans le portail).

Le jour de la bascule, sur la machine qui héberge la V1 :

1. Supprime à la main les salons « *'s Palace* » encore ouverts : la V2 ne touche qu'aux salons qu'elle a créés elle-même.
2. `git pull`
3. Mets à jour `.env` : `DISCORD_SECRET_CLIENT` devient `DISCORD_TOKEN`, et ajoute `DISCORD_GUILD_ID` et les identifiants de salons (pars de `.env.example`).
4. `sudo chown -R 1000:1000 data` : la V1 tournait en administrateur (root), la V2 tourne avec un utilisateur limité (UID 1000).
5. `docker compose up -d --build --remove-orphans` : `--remove-orphans` arrête l'ancien conteneur `mingati_bot_prod`. Sans ça, deux bots répondraient en même temps.

## 11. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `Invalid configuration, check your .env file` | Variable obligatoire absente ou identifiant qui n'est pas un nombre | Comparer `.env` avec `.env.example` |
| `Discord rejected DISCORD_TOKEN` | Token révoqué ou mal copié | Régénérer le token (étape 2) |
| `A privileged intent is enabled in code...` | Option activée sans cocher son intent | Cocher l'intent dans *Bot → Privileged Gateway Intents* |
| `Bot is not a member of guild ...` | Mauvais `DISCORD_GUILD_ID` ou bot pas invité | Vérifier l'identifiant, réinviter le bot |
| Les commandes `/` n'apparaissent pas | Scope `applications.commands` oublié | Réinviter le bot avec les deux scopes (étape 3) |
| `PermissionError` sur `data/` | Dossier `data` créé par root | `sudo chown -R 1000:1000 data` |
| `unable to open database file` | Dossier `data/` absent | `mkdir -p data` |
| Rien ne se passe en rejoignant « Créer un vocal » | Identifiant du salon absent ou faux | Vérifier `CHANNEL_CREATE_VOICE_*_ID` ; le log de démarrage signale un salon introuvable |
| « Il me manque des permissions Discord » en verrouillant ou invitant | `Manage Roles` absent | Donner `Manage Roles` au rôle du bot, placé en bas de la liste |
| Vocal créé mais membre pas déplacé | `Move Members` ou `Connect` absent sur la catégorie | Vérifier les permissions du rôle du bot sur la catégorie |
| Aucun jeu gratuit annoncé | `CHANNEL_FREE_GAMES_ID` absent, ou premier passage silencieux | `/freegames status` et le log de démarrage |
| `/game-night` refusé | `Create Events` absent | Ajouter la permission au rôle du bot |
| Le renommage d'un vocal échoue | Discord limite fortement les renommages de salon | Attendre quelques minutes |
| Billy dit qu'il dort | `LLM_MODEL` ou la clé IA manquant | Remplir la section Billy de `.env` |
| Message `PyNaCl is not installed` dans les logs | Normal : le bot ne joue pas de son | Rien à faire |
| Le bot ne revient pas après un redémarrage du Pi | Docker ne démarre pas au boot | `sudo systemctl enable docker` |
