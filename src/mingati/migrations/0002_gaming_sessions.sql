CREATE TABLE gaming_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER UNIQUE,
    host_id INTEGER NOT NULL,
    game TEXT NOT NULL,
    platform TEXT NOT NULL,
    mode TEXT,
    max_players INTEGER NOT NULL CHECK (max_players BETWEEN 2 AND 20),
    starts_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    voice_channel_id INTEGER,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX gaming_sessions_expires_at ON gaming_sessions (expires_at);
CREATE INDEX gaming_sessions_host ON gaming_sessions (guild_id, host_id);

CREATE TABLE gaming_session_members (
    session_id INTEGER NOT NULL REFERENCES gaming_sessions (id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    joined_at INTEGER NOT NULL DEFAULT (unixepoch()),
    PRIMARY KEY (session_id, user_id)
);

CREATE INDEX gaming_session_members_user ON gaming_session_members (user_id);
