"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import {
  ChapterSummary,
  CharacterDetail,
  CharacterSummary,
  ChatResponse,
  getCharacterDetail,
  listChapters,
  listCharacters,
  postRoleChat,
} from "@/lib/api";
import { StoryShell } from "../../components/StoryShell";

type ChatRow = { role: "user" | "assistant"; text: string; meta?: string };

export default function ChatPage() {
  const params = useParams<{ bookId: string }>();
  const bookId = params.bookId;
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [characters, setCharacters] = useState<CharacterSummary[]>([]);
  const [chapterIndex, setChapterIndex] = useState<number | null>(null);
  const [roleName, setRoleName] = useState("Narrator");
  const [message, setMessage] = useState("");
  const [rows, setRows] = useState<ChatRow[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [activeCharacter, setActiveCharacter] = useState<CharacterDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const roleOptions = useMemo(
    () => ["Narrator", ...characters.map((c) => c.canonical_name)],
    [characters]
  );

  useEffect(() => {
    if (!bookId) return;
    listChapters(bookId)
      .then((items) => {
        setChapters(items);
        if (items[0]) setChapterIndex(items[0].chapter_index);
      })
      .catch((e: Error) => setError(e.message));
    listCharacters(bookId)
      .then(setCharacters)
      .catch((e: Error) => setError(e.message));
  }, [bookId]);

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
    setLoading(true);
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
          meta: `风险: ${resp.spoiler_risk} · 模型: ${resp.llm_model || "n/a"}`,
        },
      ]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <StoryShell
      title="角色对话"
      subtitle="与书中人物并肩而谈"
      nav={[
        { href: "/", label: "首页" },
        { href: "/library", label: "书库" },
        { href: `/reader/${bookId}`, label: "阅读" },
        { href: `/chat/${bookId}`, label: "对话" },
        { href: `/visual/${bookId}`, label: "立绘" },
      ]}
    >
      <section className="paper-grid chat-layout">
        <article className="paper-card wide chat-stage">
          <div className="row-actions">
            <label className="control">
              角色
              <select value={roleName} onChange={(e) => setRoleName(e.target.value)}>
                {roleOptions.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label className="control">
              阅读进度
              <select value={chapterIndex ?? ""} onChange={(e) => setChapterIndex(Number(e.target.value))}>
                {chapters.map((c) => (
                  <option key={c.id} value={c.chapter_index}>
                    第{c.chapter_index}章
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="chat-board">
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
              placeholder="输入你的话..."
            />
            <button className="btn-primary" type="submit" disabled={loading}>
              {loading ? "回复中..." : "发送"}
            </button>
          </form>

          {sessionId ? <p className="muted">Session: {sessionId}</p> : null}
          {error ? <p className="error">{error}</p> : null}
        </article>

        {activeCharacter ? (
          <article className="paper-card role-card">
            <h2>{activeCharacter.canonical_name}</h2>
            <p className="muted">首次出现：第{activeCharacter.first_chapter_index ?? "-"}章</p>
            {activeCharacter.card ? (
              <div className="role-sections">
                <section>
                  <h4>性格</h4>
                  <p>{activeCharacter.card.personality_summary || "暂无"}</p>
                </section>
                <section>
                  <h4>说话风格</h4>
                  <p>{activeCharacter.card.speaking_style || "暂无"}</p>
                </section>
                <section>
                  <h4>价值观与禁忌</h4>
                  <p>{activeCharacter.card.values_and_taboo || "暂无"}</p>
                </section>
              </div>
            ) : (
              <p className="muted">该角色暂无完整角色卡。</p>
            )}
            <div className="row-actions top-gap">
              <Link href={`/reader/${bookId}`} className="btn-ghost">回到阅读</Link>
              <Link href={`/visual/${bookId}`} className="btn-ghost">生成立绘</Link>
            </div>
          </article>
        ) : (
          <article className="paper-card role-card">
            <h2>角色档案</h2>
            <p className="muted">当前角色没有可展示的人物卡，或你正在使用 Narrator 模式。</p>
          </article>
        )}
      </section>
    </StoryShell>
  );
}

