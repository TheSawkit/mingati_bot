CREATE TABLE free_games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    image_url TEXT,
    starts_at INTEGER,
    ends_at INTEGER,
    offer_key TEXT NOT NULL UNIQUE,
    first_seen_at INTEGER NOT NULL DEFAULT (unixepoch()),
    published_at INTEGER,
    message_id INTEGER
);

CREATE INDEX free_games_pending ON free_games (published_at, ends_at);
CREATE INDEX free_games_source ON free_games (source, ends_at);

CREATE TABLE game_sources (
    name TEXT PRIMARY KEY,
    last_success_at INTEGER,
    last_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    last_error_at INTEGER
);
