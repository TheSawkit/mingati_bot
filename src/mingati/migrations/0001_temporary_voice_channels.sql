CREATE TABLE temporary_voice_channels (
    channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    trigger_channel_id INTEGER NOT NULL,
    panel_message_id INTEGER,
    is_locked INTEGER NOT NULL DEFAULT 0 CHECK (is_locked IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE UNIQUE INDEX temporary_voice_channels_owner
    ON temporary_voice_channels (guild_id, owner_id);
