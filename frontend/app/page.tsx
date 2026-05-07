"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  API_BASE_URL,
  Book,
  CharacterSummary,
  ChapterDetail,
  ChapterSummary,
  MediaAsset,
  RelationshipEdge,
  RelationshipGraphNodeMetric,
  VisualJobStatusResponse,
  enqueueVisualJob,
  fetchHealth,
  getChapter,
  getRelationshipGraph,
  getRelationshipGraphNodes,
  getVisualJobStatus,
  listBooks,
  listCharacters,
  listChapters,
  listMediaAssets,
  postRoleChat,
} from "@/lib/api";

type ChatItem = { role: "user" | "assistant"; text: string; meta?: string };

function buildGraph(nodes: RelationshipGraphNodeMetric[], edges: RelationshipEdge[], chapterCap: number) {
  const filteredEdges = edges.filter((e) => (e.last_chapter_index ?? 0) <= chapterCap);
  const activeIds = new Set<string>();
  filteredEdges.forEach((e) => {
    activeIds.add(e.source_character_id);
    activeIds.add(e.target_character_id);
  });
  const picked = nodes
    .filter((n) => activeIds.has(n.character_id))
    .sort((a, b) => b.weighted_degree - a.weighted_degree)
    .slice(0, 20);
  const pickedIdSet = new Set(picked.map((n) => n.character_id));
  const visibleEdges = filteredEdges.filter(
    (e) => pickedIdSet.has(e.source_character_id) && pickedIdSet.has(e.target_character_id)
  );
  const cx = 380;
  const cy = 180;
  const radius = 130;
  const visibleNodes = picked.map((n, i) => {
    const angle = (Math.PI * 2 * i) / Math.max(picked.length, 1);
    return {
      id: n.character_id,
      name: n.canonical_name,
      degree: n.degree,
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
    };
  });
  return { visibleNodes, visibleEdges };
}

export default function HomePage() {
  const [health, setHealth] = useState("checking");
  const [uiError, setUiError] = useState("");
  const [books, setBooks] = useState<Book[]>([]);
  const [selectedBookId, setSelectedBookId] = useState("");
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [selectedChapterIndex, setSelectedChapterIndex] = useState<number | null>(null);
  const [chapterDetail, setChapterDetail] = useState<ChapterDetail | null>(null);
  const [characters, setCharacters] = useState<CharacterSummary[]>([]);
  const [selectedCharacterId, setSelectedCharacterId] = useState("");
  const [chatRoleName, setChatRoleName] = useState("Narrator");
  const [chatInput, setChatInput] = useState("");
  const [chatItems, setChatItems] = useState<ChatItem[]>([]);
  const [graphEdges, setGraphEdges] = useState<RelationshipEdge[]>([]);
  const [graphNodes, setGraphNodes] = useState<RelationshipGraphNodeMetric[]>([]);
  const [graphChapterCap, setGraphChapterCap] = useState(1);
  const [focusNodeId, setFocusNodeId] = useState("");
  const [visualJob, setVisualJob] = useState<VisualJobStatusResponse | null>(null);
  const [visualPolling, setVisualPolling] = useState(false);
  const [latestAsset, setLatestAsset] = useState<MediaAsset | null>(null);
  const [visualAssetType, setVisualAssetType] = useState<"portrait" | "character_card" | "scene">("portrait");

  const maxChapter = useMemo(
    () => (chapters.length ? Math.max(...chapters.map((c) => c.chapter_index)) : 1),
    [chapters]
  );
  const graph = useMemo(
    () => buildGraph(graphNodes, graphEdges, graphChapterCap),
    [graphNodes, graphEdges, graphChapterCap]
  );
  const graphNodeMap = useMemo(() => {
    const map = new Map<string, { x: number; y: number; name: string; degree: number }>();
    graph.visibleNodes.forEach((n) => map.set(n.id, n));
    return map;
  }, [graph.visibleNodes]);
  const roleOptions = useMemo(() => ["Narrator", ...characters.map((c) => c.canonical_name)], [characters]);
  const focusEdges = useMemo(
    () =>
      graph.visibleEdges.filter(
        (e) => !focusNodeId || e.source_character_id === focusNodeId || e.target_character_id === focusNodeId
      ),
    [graph.visibleEdges, focusNodeId]
  );

  useEffect(() => {
    fetchHealth().then((r) => setHealth(r.status)).catch(() => setHealth("down"));
    listBooks().then((items) => {
      setBooks(items);
      if (items[0]) setSelectedBookId(items[0].id);
    });
  }, []);

  useEffect(() => {
    if (!selectedBookId) return;
    listChapters(selectedBookId).then((items) => {
      setChapters(items);
      const first = items[0]?.chapter_index ?? null;
      setSelectedChapterIndex(first);
      if (first) setGraphChapterCap(first);
    });
    listCharacters(selectedBookId).then((items) => {
      setCharacters(items);
      if (items[0]) {
        setSelectedCharacterId(items[0].id);
        setChatRoleName(items[0].canonical_name);
      }
    });
    getRelationshipGraph(selectedBookId).then(setGraphEdges);
    getRelationshipGraphNodes(selectedBookId).then(setGraphNodes);
  }, [selectedBookId]);

  useEffect(() => {
    if (!selectedBookId || selectedChapterIndex == null) return;
    getChapter(selectedBookId, selectedChapterIndex)
      .then(setChapterDetail)
      .catch((e: Error) => setUiError(e.message));
  }, [selectedBookId, selectedChapterIndex]);

  useEffect(() => {
    if (!selectedBookId || !selectedCharacterId) {
      setLatestAsset(null);
      return;
    }
    listMediaAssets(selectedBookId, visualAssetType, selectedCharacterId || undefined).then((items) => {
      setLatestAsset(items[0] || null);
    });
  }, [selectedBookId, selectedCharacterId, visualJob?.status, visualAssetType]);

  useEffect(() => {
    if (!selectedBookId || !visualJob || visualJob.status === "completed" || visualJob.status === "failed") {
      setVisualPolling(false);
      return;
    }
    setVisualPolling(true);
    const timer = window.setTimeout(async () => {
      try {
        const latest = await getVisualJobStatus(selectedBookId, visualJob.job_id);
        setVisualJob(latest);
      } catch (e) {
        setUiError((e as Error).message);
      }
    }, 1800);
    return () => window.clearTimeout(timer);
  }, [selectedBookId, visualJob]);

  const submitChat = async (event: FormEvent) => {
    event.preventDefault();
    const text = chatInput.trim();
    if (!text || !selectedBookId) return;
    setChatItems((prev) => [...prev, { role: "user", text }]);
    setChatInput("");
    try {
      const resp = await postRoleChat({
        book_id: selectedBookId,
        role_name: chatRoleName,
        message: text,
        chapter_index: selectedChapterIndex,
      });
      setChatItems((prev) => [
        ...prev,
        { role: "assistant", text: resp.answer, meta: `风险: ${resp.spoiler_risk} | 模型: ${resp.llm_model || "n/a"}` },
      ]);
    } catch (e) {
      setUiError((e as Error).message);
    }
  };

  const submitVisualJob = async () => {
    if (!selectedBookId) return;
    if (visualAssetType !== "scene" && !selectedCharacterId) return;
    try {
      const created = await enqueueVisualJob(selectedBookId, {
        asset_type: visualAssetType,
        character_id: visualAssetType === "scene" ? undefined : selectedCharacterId,
        chapter_index: selectedChapterIndex || undefined,
      });
      const status = await getVisualJobStatus(selectedBookId, created.job_id);
      setVisualJob(status);
    } catch (e) {
      setUiError((e as Error).message);
    }
  };

  return (
    <main className="workspace">
      <header className="topbar">
        <div>
          <h1>StoryVerse 阅读工坊</h1>
          <p>多智能体阅读体验：文本 Agent + 视觉 Agent 协同</p>
        </div>
        <div className="health-box">
          <span>API: {API_BASE_URL}</span>
          <strong data-state={health}>{health}</strong>
        </div>
      </header>

      {uiError ? <p className="error">{uiError}</p> : null}

      <section className="layout">
        <aside className="sidebar">
          <article className="panel">
            <h2>书籍</h2>
            <ul className="book-list">
              {books.map((b) => (
                <li key={b.id}>
                  <button className={selectedBookId === b.id ? "active" : ""} onClick={() => setSelectedBookId(b.id)} type="button">
                    <span className="title">{b.title}</span>
                    <span className={`status status-${b.status}`}>{b.status}</span>
                  </button>
                </li>
              ))}
            </ul>
          </article>

          <article className="panel">
            <h2>章节目录</h2>
            <ul className="chapter-list">
              {chapters.map((c) => (
                <li key={c.id}>
                  <button className={selectedChapterIndex === c.chapter_index ? "active" : ""} onClick={() => setSelectedChapterIndex(c.chapter_index)} type="button">
                    <span className="index">#{c.chapter_index}</span>
                    <span className="title">{c.title}</span>
                  </button>
                </li>
              ))}
            </ul>
          </article>

          <article className="panel">
            <h2>人物</h2>
            <ul className="character-list">
              {characters.map((c) => (
                <li key={c.id}>
                  <button
                    className={selectedCharacterId === c.id ? "active" : ""}
                    type="button"
                    onClick={() => {
                      setSelectedCharacterId(c.id);
                      setChatRoleName(c.canonical_name);
                    }}
                  >
                    <span className="title">{c.canonical_name}</span>
                    <span className="meta">提及 {c.mention_count} · 置信 {c.confidence.toFixed(2)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </article>
        </aside>

        <article className="reader panel">
          <section className="chapter-content">
            <h3>{chapterDetail ? `第 ${chapterDetail.chapter_index} 章 · ${chapterDetail.title}` : "请选择章节"}</h3>
            {chapterDetail ? <pre>{chapterDetail.raw_text}</pre> : <p className="muted">等待加载章节内容...</p>}
          </section>

          <section className="graph-panel">
            <div className="graph-head">
              <h3>人物关系图谱</h3>
              <div className="graph-toolbar">
                <label htmlFor="graph-cap">剧情上限章节</label>
                <input id="graph-cap" type="range" min={1} max={maxChapter} value={graphChapterCap} onChange={(e) => setGraphChapterCap(Number(e.target.value))} />
                <span className="muted">第 {graphChapterCap} 章</span>
              </div>
            </div>
            <div className="graph-canvas-wrap">
              <svg className="graph-canvas" viewBox="0 0 760 360">
                {graph.visibleEdges.map((e) => {
                  const s = graphNodeMap.get(e.source_character_id);
                  const t = graphNodeMap.get(e.target_character_id);
                  if (!s || !t) return null;
                  const active = focusNodeId && (e.source_character_id === focusNodeId || e.target_character_id === focusNodeId);
                  return <line key={e.id} x1={s.x} y1={s.y} x2={t.x} y2={t.y} stroke={active ? "#99541c" : "rgba(88,65,38,.33)"} strokeWidth={active ? 3 : 1.5} />;
                })}
                {graph.visibleNodes.map((n) => (
                  <g key={n.id} onClick={() => setFocusNodeId(n.id)} style={{ cursor: "pointer" }}>
                    <circle cx={n.x} cy={n.y} r={Math.min(22, 8 + n.degree)} fill={focusNodeId === n.id ? "#c9782c" : "#d8b48a"} stroke="#6f3d18" />
                    <text x={n.x} y={n.y + 20} textAnchor="middle" className="graph-label">{n.name}</text>
                  </g>
                ))}
              </svg>
            </div>
            <div className="graph-evidence-panel">
              <h4>关系证据 {focusNodeId ? "（已选人物）" : ""}</h4>
              <ul className="graph-evidence-list">
                {focusEdges.slice(0, 8).map((e) => (
                  <li key={e.id}>
                    <strong>{e.source_name}</strong> → <strong>{e.target_name}</strong>
                    <span className="muted"> · {e.relation_type} · 强度 {e.strength}</span>
                    <div className="muted">章 {e.first_chapter_index ?? "-"} - {e.last_chapter_index ?? "-"}</div>
                    <div>{e.evidence_excerpt || "(无证据片段)"}</div>
                  </li>
                ))}
              </ul>
            </div>
          </section>

          <section className="graph-panel">
            <div className="graph-head">
              <h3>视觉 Agent（立绘任务）</h3>
            </div>
            <div className="graph-toolbar">
              <select
                value={visualAssetType}
                onChange={(e) => setVisualAssetType(e.target.value as "portrait" | "character_card" | "scene")}
              >
                <option value="portrait">人物立绘</option>
                <option value="character_card">角色卡图</option>
                <option value="scene">场景图</option>
              </select>
              <button type="button" className="ghost-btn" onClick={submitVisualJob}>
                提交视觉任务
              </button>
              {visualJob ? <span className="muted">任务状态：{visualJob.status}{visualPolling ? "（轮询中）" : ""}</span> : null}
            </div>
            {latestAsset ? (
              <div className="portrait-media" style={{ marginTop: "0.7rem" }}>
                <img src={latestAsset.storage_url.startsWith("/") ? `${API_BASE_URL}${latestAsset.storage_url}` : latestAsset.storage_url} alt="latest portrait" />
              </div>
            ) : <p className="muted">当前人物暂无视觉资产。</p>}
          </section>

          <section className="chat-panel">
            <div className="chat-head">
              <h3>角色对话</h3>
              <div className="chat-controls">
                <label htmlFor="chat-role">扮演角色</label>
                <select id="chat-role" value={chatRoleName} onChange={(e) => setChatRoleName(e.target.value)}>
                  {roleOptions.map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </div>
            </div>
            <div className="chat-messages">
              {chatItems.map((m, i) => (
                <article key={`${m.role}-${i}`} className={`chat-message chat-${m.role}`}>
                  <header><strong>{m.role === "user" ? "你" : chatRoleName}</strong></header>
                  <p>{m.text}</p>
                  {m.meta ? <div className="chat-meta">{m.meta}</div> : null}
                </article>
              ))}
            </div>
            <form className="chat-input-box" onSubmit={submitChat}>
              <textarea value={chatInput} onChange={(e) => setChatInput(e.target.value)} rows={4} placeholder="输入你想对角色说的话..." />
              <button type="submit">发送</button>
            </form>
          </section>
        </article>
      </section>
    </main>
  );
}
