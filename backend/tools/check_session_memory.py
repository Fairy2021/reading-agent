from sqlalchemy import text

from app.db.session import engine


def main() -> None:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "select session_id, role_name, emotion_tag, "
                "left(memory_summary, 120) as ms, last_chapter_index "
                "from session_memories order by updated_at desc limit 5"
            )
        ).all()
    print(rows)


if __name__ == "__main__":
    main()

