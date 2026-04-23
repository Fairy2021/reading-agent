from sqlalchemy import text

from app.db.session import engine

STATEMENTS = [
    "ALTER TABLE books ADD COLUMN IF NOT EXISTS skill_checkpoint_chapter INTEGER DEFAULT 0",
    "ALTER TABLE characters ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE",
    (
        "CREATE TABLE IF NOT EXISTS character_states ("
        "id VARCHAR(36) PRIMARY KEY, "
        "character_id VARCHAR(36) NOT NULL REFERENCES characters(id) ON DELETE CASCADE, "
        "chapter_index INTEGER NOT NULL, "
        "emotional_state TEXT DEFAULT '', "
        "stance TEXT DEFAULT '', "
        "current_goal TEXT DEFAULT '', "
        "relation_snapshot TEXT DEFAULT '', "
        "source_summary TEXT DEFAULT '', "
        "created_at TIMESTAMPTZ DEFAULT now(), "
        "updated_at TIMESTAMPTZ DEFAULT now(), "
        "CONSTRAINT uq_character_state_chapter UNIQUE(character_id, chapter_index)"
        ")"
    ),
    "CREATE INDEX IF NOT EXISTS ix_character_states_character_id ON character_states(character_id)",
    "CREATE INDEX IF NOT EXISTS ix_character_states_chapter_index ON character_states(chapter_index)",
    (
        "CREATE TABLE IF NOT EXISTS session_memories ("
        "id VARCHAR(36) PRIMARY KEY, "
        "book_id VARCHAR(36) NOT NULL REFERENCES books(id) ON DELETE CASCADE, "
        "session_id VARCHAR(128) NOT NULL, "
        "role_name VARCHAR(120) NOT NULL, "
        "emotion_tag VARCHAR(64) DEFAULT 'neutral', "
        "memory_summary TEXT DEFAULT '', "
        "last_user_message TEXT DEFAULT '', "
        "last_assistant_message TEXT DEFAULT '', "
        "last_chapter_index INTEGER NULL, "
        "created_at TIMESTAMPTZ DEFAULT now(), "
        "updated_at TIMESTAMPTZ DEFAULT now(), "
        "CONSTRAINT uq_session_memory_scope UNIQUE(book_id, session_id, role_name)"
        ")"
    ),
    "CREATE INDEX IF NOT EXISTS ix_session_memories_book_id ON session_memories(book_id)",
    "CREATE INDEX IF NOT EXISTS ix_session_memories_session_id ON session_memories(session_id)",
    "CREATE INDEX IF NOT EXISTS ix_session_memories_role_name ON session_memories(role_name)",
]


def main() -> None:
    with engine.begin() as conn:
        for sql in STATEMENTS:
            conn.execute(text(sql))
    print("schema_migrated")


if __name__ == "__main__":
    main()

