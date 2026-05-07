"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import {
  ChapterDetail,
  ChapterSummary,
  CharacterDetail,
  CharacterSummary,
  ChatResponse,
  getChapter,
  getCharacterDetail,
  listChapters,
  listCharacters,
  postRoleChat,
} from "@/lib/api";

type ChatRow = { role: "user" | "assistant"; text: string; meta?: string };

export default function ReaderPage() {
  const params = useParams<{ bookId: string }>();
  const bookId = params.bookId;

  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [chapterIndex, setChapterIndex] = useState<number | null>(null);
  const [chapter, setChapter] = useState<ChapterDetail | null>(null);

  const [characters, setCharacters] = useState<CharacterSummary[]>([]);
  const [roleName, setRoleName] = useState("Narrator");
  const [activeCharacter, setActiveCharacter] = useState<CharacterDetail | null>(null);

  const [message, setMessage] = useState("");
  const [rows, setRows] = useState<ChatRow[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const [loadingChapter, setLoadingChapter] = useState(false);
  const [loadingChat, setLoadingChat] = useState(false);
  const [error, setError] = useState("");

  const roleOptions = useMemo(
    () => ["Narrator", ...characters.map((c) => c.canonical_name)],
    [characters]
  );

  const chapterPos = useMemo(() => {
    if (chapterIndex === null) return -1;
    return chapters.findIndex((item) => item.chapter_index === chapterIndex);
  }, [chapters, chapterIndex]);

  const prevChapter = chapterPos > 0 ? chapters[chapterPos - 1] : null;
  const nextChapter = chapterPos >= 0 && chapterPos < chapters.length - 1 ? chapters[chapterPos + 1] : null;

  useEffect(() => {
    if (!bookId) return;
    setError("");
    listChapters(bookId)
      .then((items) => {
        setChapters(items);
        if (items[0]) {
          setChapterIndex(items[0].chapter_index);
        }
      })
      .catch((e: Error) => setError(e.message));

    listCharacters(bookId)
      .then(setCharacters)
      .catch((e: Error) => setError(e.message));
  }, [bookId]);

  useEffect(() => {
    if (!bookId || chapterIndex === null) return;
    setLoadingChapter(true);
    setError("");
    getChapter(bookId, chapterIndex)
      .then(setChapter)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoadingChapter(false));
  }, [bookId, chapterIndex]);

  useEffect(() => {
    if (!bookId || roleName === "Narrator") {
      setActiveCharacter(null);
      return;
    }
    const matched = characters.find((c) => c.canonical_name === roleName);
    if (!matched) {
      setActiveCharacter(null);
      return;
    }
    getCharacterDetail(bookId, matched.id)
      .then(setActiveCharacter)
      .catch(() => setActiveCharacter(null));
  }, [bookId, roleName, characters]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const text = message.trim();
    if (!text || !bookId) return;
    setRows((prev) => [...prev, { role: "user", text }]);
    setMessage("");
    setLoadingChat(true);
    setError("");
    try {
      const resp: ChatResponse = await postRoleChat({
        book_id: bookId,
        role_name: roleName,
        message: text,
        chapter_index: chapterIndex || undefined,
        session_id: sessionId || undefined,
      });
      setSessionId(resp.session_id || sessionId);
      setRows((prev) => [
        ...prev,
        {
          role: "assistant",
          text: resp.answer,
          meta: `risk=${resp.spoiler_risk} | model=${resp.llm_model || "n/a"}`,
        },
      ]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoadingChat(false);
    }
  };

  return (
    <main className="reader-scene">
      <div className="reader-ambient reader-ambient-a" />
      <div className="reader-ambient reader-ambient-b" />
      <div className="reader-ambient reader-ambient-c" />

      <header className="reader-topbar glass-panel">
        <div className="reader-title-block">
          <span className="reader-badge">StoryVerse · 沉浸式名著阅读</span>
          <h1>太虚卷 · 旁观入梦</h1>
          <p>单页正文、章节目录与人物对话同屏展开。你可以边读边聊，且始终受进度守卫保护。</p>
        </div>
        <div className="reader-top-actions">
          <Link href="/library" className="btn-ghost">回书库</Link>
          <Link href={`/visual/${bookId}`} className="btn-ghost">去立绘库</Link>
        </div>
      </header>

      <section className="reader-grid">
        <aside className="glass-panel chapter-rail">
          <div className="panel-kicker">卷帙目录</div>
          <div className="book-meta-stack">
            <div>
              <h2>章节导航</h2>
              <p className="muted">点选章节像翻页，沿着文本顺序缓慢进入故事。</p>
            </div>
            <div className="page-nav">
              <button
                type="button"
                className="btn-ghost"
                onClick={() => prevChapter && setChapterIndex(prevChapter.chapter_index)}
                disabled={!prevChapter}
              >
                上一章
              </button>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => nextChapter && setChapterIndex(nextChapter.chapter_index)}
                disabled={!nextChapter}
              >
                下一章
              </button>
            </div>
          </div>
          <ul className="chapter-list chapter-list-dream">
            {chapters.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  className={`chapter-chip ${chapterIndex === c.chapter_index ? "active" : ""}`}
                  onClick={() => setChapterIndex(c.chapter_index)}
                >
                  <span className="chapter-pill">{c.chapter_index}</span>
                  <span className="chapter-title">{c.title}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <article className="glass-panel book-stage">
          <div className="book-sheen" />
          <div className="book-header">
            <div>
              <div className="panel-kicker">正文页</div>
              <h2>{chapter?.title || "请选择章节"}</h2>
            </div>
            <div className="chapter-indicator">
              <span className="dream-chip">当前进度：第 {chapterIndex ?? "-"} 章</span>
              <span className="dream-chip">单页阅读</span>
            </div>
          </div>

          <div className="book-page-frame">
            <div className="page-edge page-edge-left" />
            <div className="page-edge page-edge-right" />
            {loadingChapter ? (
              <div className="chapter-loading">章节加载中...</div>
            ) : (
              <pre className="chapter-paper dream-paper">{chapter?.raw_text || ""}</pre>
            )}
          </div>
        </article>

        <aside className="glass-panel dialogue-stage">
          <div className="panel-kicker">书页右侧 · 角色在场</div>
          <div className="dialogue-head">
            <div>
              <h2>人物对话</h2>
              <p className="muted">直接在阅读旁边和角色交流，不需要跳转页面。</p>
            </div>
          </div>

          <div className="chat-role-pills">
            {roleOptions.map((name) => (
              <button
                key={name}
                type="button"
                className={`role-pill ${roleName === name ? "active" : ""}`}
                onClick={() => setRoleName(name)}
              >
                {name}
              </button>
            ))}
          </div>

          {activeCharacter ? (
            <section className="role-mini-card role-mini-card-dream">
              <div className="role-mini-head">
                <div className="avatar-glow">{activeCharacter.canonical_name.slice(0, 1)}</div>
                <div>
                  <h3>{activeCharacter.canonical_name}</h3>
                  <p className="muted">首次出现：第 {activeCharacter.first_chapter_index ?? "-"} 章</p>
                </div>
              </div>
              <p>{activeCharacter.card?.personality_summary || "暂无完整角色卡"}</p>
            </section>
          ) : (
            <section className="role-mini-card role-mini-card-empty">
              <h3>Narrator</h3>
              <p>当前是旁白模式。选择某位角色后，这里会自动显示其人物卡。</p>
            </section>
          )}

          <div className="chat-board dream-chat-board">
            {rows.map((row, idx) => (
              <article key={`${row.role}-${idx}`} className={`bubble ${row.role}`}>
                <h4>{row.role === "user" ? "你" : roleName}</h4>
                <p>{row.text}</p>
                {row.meta ? <small>{row.meta}</small> : null}
              </article>
            ))}
          </div>

          <form className="chat-editor" onSubmit={submit}>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={3}
              placeholder="问问角色对当前章节的看法..."
            />
            <button className="btn-primary" type="submit" disabled={loadingChat}>
              {loadingChat ? "回复中..." : "发送对话"}
            </button>
          </form>

          {sessionId ? <p className="muted">session: {sessionId}</p> : null}
          {error ? <p className="error">{error}</p> : null}
        </aside>
      </section>
    </main>
  );
}
