"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import {
  API_BASE_URL,
  CharacterDetail,
  CharacterSummary,
  ChapterSummary,
  MediaAsset,
  VisualJobCreateRequest,
  VisualJobStatusResponse,
  enqueueVisualJob,
  getCharacterDetail,
  getVisualJobStatus,
  listCharacters,
  listChapters,
  listMediaAssets,
} from "@/lib/api";
import { StoryShell } from "../../components/StoryShell";

type AssetType = "portrait" | "character_card" | "scene";

function assetUrl(raw: string) {
  return raw.startsWith("/") ? `${API_BASE_URL}${raw}` : raw;
}

export default function VisualPage() {
  const params = useParams<{ bookId: string }>();
  const bookId = params.bookId;
  const storageKey = `visual:last-character:${bookId}`;
  const [characters, setCharacters] = useState<CharacterSummary[]>([]);
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [assetType, setAssetType] = useState<AssetType>("portrait");
  const [characterId, setCharacterId] = useState("");
  const [chapterIndex, setChapterIndex] = useState<number | null>(null);
  const [job, setJob] = useState<VisualJobStatusResponse | null>(null);
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [activeCharacter, setActiveCharacter] = useState<CharacterDetail | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!bookId) return;
    const remembered = typeof window !== "undefined" ? window.localStorage.getItem(storageKey) : null;
    listCharacters(bookId)
      .then((items) => {
        setCharacters(items);
        if (remembered && items.some((c) => c.id === remembered)) {
          setCharacterId(remembered);
        } else if (items[0]) {
          setCharacterId(items[0].id);
        }
      })
      .catch((e: Error) => setError(e.message));
    listChapters(bookId)
      .then((items) => {
        setChapters(items);
        if (items[0]) setChapterIndex(items[0].chapter_index);
      })
      .catch((e: Error) => setError(e.message));
  }, [bookId, storageKey]);

  useEffect(() => {
    if (!bookId) return;
    listMediaAssets(bookId, assetType, undefined)
      .then(setAssets)
      .catch((e: Error) => setError(e.message));
  }, [bookId, assetType, job?.status]);

  useEffect(() => {
    if (!bookId || !characterId) {
      setActiveCharacter(null);
      return;
    }
    if (typeof window !== "undefined") {
      window.localStorage.setItem(storageKey, characterId);
    }
    getCharacterDetail(bookId, characterId)
      .then(setActiveCharacter)
      .catch(() => setActiveCharacter(null));
  }, [bookId, characterId, storageKey]);

  useEffect(() => {
    if (!bookId || !job || job.status === "completed" || job.status === "failed") return;
    const timer = window.setTimeout(async () => {
      try {
        const latest = await getVisualJobStatus(bookId, job.job_id);
        setJob(latest);
      } catch (e) {
        setError((e as Error).message);
      }
    }, 1800);
    return () => window.clearTimeout(timer);
  }, [bookId, job]);

  const latestByCharacter = useMemo(() => {
    const map = new Map<string, MediaAsset>();
    for (const asset of assets) {
      const key = asset.character_id || "__scene__";
      const existing = map.get(key);
      if (!existing || asset.version > existing.version) {
        map.set(key, asset);
      }
    }
    return map;
  }, [assets]);

  const selectedAsset = latestByCharacter.get(characterId);

  const submit = async () => {
    if (!bookId) return;
    if (assetType !== "scene" && !characterId) return;
    setLoading(true);
    setError("");
    try {
      const payload: VisualJobCreateRequest = {
        asset_type: assetType,
        character_id: assetType === "scene" ? undefined : characterId,
        chapter_index: chapterIndex || undefined,
      };
      const created = await enqueueVisualJob(bookId, payload);
      const latest = await getVisualJobStatus(bookId, created.job_id);
      setJob(latest);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <StoryShell
      title="立绘与场景图"
      subtitle="Visual Agent 任务卡片库"
      nav={[
        { href: "/", label: "首页" },
        { href: "/library", label: "书库" },
        { href: `/reader/${bookId}`, label: "阅读" },
        { href: `/chat/${bookId}`, label: "对话" },
        { href: `/visual/${bookId}`, label: "立绘" },
      ]}
    >
      <section className="paper-grid visual-layout">
        <article className="paper-card visual-hero sectioned glow">
          <div className="dream-banner">
            <div>
              <h2>绘梦工坊</h2>
              <p>为人物与章节生成立绘、角色卡与场景图，形成可回看的资产库。</p>
            </div>
            <div className="dream-caption">
              <span className="dream-chip">角色立绘</span>
              <span className="dream-chip">任务追踪</span>
            </div>
          </div>
          <h2>创建任务</h2>
          <div className="form-stack">
            <label>
              类型
              <select value={assetType} onChange={(e) => setAssetType(e.target.value as AssetType)}>
                <option value="portrait">人物立绘</option>
                <option value="character_card">角色卡</option>
                <option value="scene">场景图</option>
              </select>
            </label>
            <label>
              人名
              <select
                value={characterId}
                onChange={(e) => setCharacterId(e.target.value)}
                disabled={assetType === "scene"}
              >
                {characters.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.canonical_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              章节
              <select value={chapterIndex ?? ""} onChange={(e) => setChapterIndex(Number(e.target.value))}>
                {chapters.map((c) => (
                  <option key={c.id} value={c.chapter_index}>
                    第{c.chapter_index}章
                  </option>
                ))}
              </select>
            </label>
            <button className="btn-primary" type="button" onClick={submit} disabled={loading}>
              {loading ? "提交中..." : "提交任务"}
            </button>
          </div>

          {job ? (
            <div className="hint-box">
              <div>Job: {job.job_id}</div>
              <div>状态: {job.status}</div>
              {job.error_message ? <div className="error">{job.error_message}</div> : null}
            </div>
          ) : null}
          {error ? <p className="error">{error}</p> : null}
        </article>

        <article className="paper-card wide visual-library sectioned glow">
          <div className="section-caption">任务卡片库</div>
          <h2>按人物保留最新版本</h2>
          <div className="task-card-grid">
            {characters.map((character) => {
              const latest = latestByCharacter.get(character.id);
              const active = character.id === characterId;
              return (
                <button
                  key={character.id}
                  type="button"
                  className={`task-person-card ${active ? "active" : ""}`}
                  onClick={() => setCharacterId(character.id)}
                >
                  <div className="thumb">
                    {latest ? (
                      <img src={assetUrl(latest.storage_url)} alt={character.canonical_name} />
                    ) : (
                      <span>暂无图像</span>
                    )}
                  </div>
                  <div className="meta">
                    <strong>{character.canonical_name}</strong>
                    <span>首次出现：第{character.first_chapter_index ?? "-"}章</span>
                    <span>最新版本：{latest ? `v${latest.version}` : "-"}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </article>

        <article className="paper-card wide visual-detail sectioned glow">
          <div className="section-caption">人物档案</div>
          {activeCharacter ? (
            <div className="visual-detail-grid">
              <div className="visual-preview">
                {selectedAsset ? (
                  <img src={assetUrl(selectedAsset.storage_url)} alt={activeCharacter.canonical_name} />
                ) : (
                  <span>暂无图像</span>
                )}
              </div>
              <div className="role-sections">
                <section>
                  <h4>{activeCharacter.canonical_name}</h4>
                  <p className="muted">首次出现：第{activeCharacter.first_chapter_index ?? "-"}章</p>
                </section>
                <section>
                  <h4>性格</h4>
                  <p>{activeCharacter.card?.personality_summary || "暂无"}</p>
                </section>
                <section>
                  <h4>说话风格</h4>
                  <p>{activeCharacter.card?.speaking_style || "暂无"}</p>
                </section>
              </div>
            </div>
          ) : (
            <p className="muted">请选择人物以查看详情。</p>
          )}
          <div className="row-actions top-gap">
            <Link href={`/chat/${bookId}`} className="btn-ghost">去和该角色对话</Link>
            <Link href={`/reader/${bookId}`} className="btn-ghost">回到阅读</Link>
          </div>
        </article>
      </section>
    </StoryShell>
  );
}
