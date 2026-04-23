"use client";

import { FormEvent, KeyboardEvent, useEffect, useMemo, useState } from "react";

import {
  API_BASE_URL,
  Book,
  CharacterPortrait,
  CharacterDetail,
  CharacterSummary,
  ChapterDetail,
  ChapterSummary,
  Citation,
  TaskStatusResponse,
  fetchHealth,
  getChapter,
  getCharacterDetail,
  getTaskStatus,
  listBooks,
  listCharacters,
  listCharacterPortraits,
  listChapters,
  postRoleChat,
  runBookSkills,
  triggerCharacterPortraitGenerate,
  uploadBookTxt
} from "@/lib/api";

const TASK_POLL_INTERVAL_MS = 1800;

type ChatRole = "user" | "assistant";

interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  meta?: string;
  citations?: Citation[];
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function normalizeTaskMessage(task: TaskStatusResponse): string {
  if (task.status === "SUCCESS") {
    const result = task.result;
    if (result && typeof result === "object" && "chapter_count" in result) {
      return `任务完成，章节数：${result.chapter_count ?? "未知"}`;
    }
    return "任务完成";
  }
  if (task.status === "FAILURE") {
    if (typeof task.result === "string") {
      return task.result;
    }
    return "任务失败，请检查后端日志";
  }
  if (task.status === "STARTED") {
    return "任务执行中...";
  }
  if (task.status === "PENDING") {
    return "任务排队中...";
  }
  return `任务状态：${task.status}`;
}

function makeMessageId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

function formatPortraitStatus(status: string): string {
  if (status === "ready") {
    return "已生成";
  }
  if (status === "generating") {
    return "生成中";
  }
  if (status === "queued") {
    return "排队中";
  }
  if (status === "failed") {
    return "生成失败";
  }
  return status || "未知";
}

function buildProxyImageUrl(imageUrl: string): string {
  if (!imageUrl) {
    return "";
  }
  if (imageUrl.startsWith("http://") || imageUrl.startsWith("https://")) {
    return `${API_BASE_URL}/api/image_proxy?url=${encodeURIComponent(imageUrl)}`;
  }
  if (imageUrl.startsWith("/")) {
    return `${API_BASE_URL}${imageUrl}`;
  }
  return imageUrl;
}

function buildAssistantMeta(params: {
  spoilerRisk: string;
  guardApplied: boolean;
  llmUsed: boolean;
  llmModel: string;
  llmError: string;
}): string {
  const items: string[] = [];
  items.push(`风险: ${params.spoilerRisk}`);
  items.push(`防剧透: ${params.guardApplied ? "已触发" : "未触发"}`);
  if (params.llmUsed) {
    items.push(`模型: ${params.llmModel || "unknown"}`);
  } else if (params.llmError) {
    items.push(`LLM失败: ${params.llmError}`);
  } else {
    items.push("LLM: 未启用");
  }
  return items.join(" | ");
}

export default function HomePage() {
  const [health, setHealth] = useState("checking");
  const [healthError, setHealthError] = useState("");

  const [books, setBooks] = useState<Book[]>([]);
  const [booksLoading, setBooksLoading] = useState(false);
  const [selectedBookId, setSelectedBookId] = useState<string>("");

  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [chaptersLoading, setChaptersLoading] = useState(false);
  const [selectedChapterIndex, setSelectedChapterIndex] = useState<number | null>(null);
  const [chapterDetail, setChapterDetail] = useState<ChapterDetail | null>(null);
  const [chapterLoading, setChapterLoading] = useState(false);

  const [characters, setCharacters] = useState<CharacterSummary[]>([]);
  const [charactersLoading, setCharactersLoading] = useState(false);
  const [selectedCharacterId, setSelectedCharacterId] = useState("");
  const [characterDetail, setCharacterDetail] = useState<CharacterDetail | null>(null);
  const [characterLoading, setCharacterLoading] = useState(false);
  const [characterPortrait, setCharacterPortrait] = useState<CharacterPortrait | null>(null);
  const [portraitLoading, setPortraitLoading] = useState(false);
  const [portraitGenerating, setPortraitGenerating] = useState(false);
  const [portraitImageFailed, setPortraitImageFailed] = useState(false);

  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  const [taskInfo, setTaskInfo] = useState<TaskStatusResponse | null>(null);
  const [taskMessage, setTaskMessage] = useState("");
  const [uiError, setUiError] = useState("");
  const [syncingSkills, setSyncingSkills] = useState(false);

  const [chatRoleName, setChatRoleName] = useState("Narrator");
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatSessionId, setChatSessionId] = useState<string>("");

  const selectedBook = useMemo(
    () => books.find((book) => book.id === selectedBookId) || null,
    [books, selectedBookId]
  );

  const roleOptions = useMemo(() => {
    const names = new Set<string>(["Narrator"]);
    characters.forEach((item) => {
      if (item.canonical_name) {
        names.add(item.canonical_name);
      }
    });
    return Array.from(names);
  }, [characters]);

  useEffect(() => {
    fetchHealth()
      .then((result) => setHealth(result.status))
      .catch((err: Error) => {
        setHealth("down");
        setHealthError(err.message);
      });
  }, []);

  useEffect(() => {
    let cancelled = false;
    setBooksLoading(true);
    listBooks()
      .then((items) => {
        if (cancelled) {
          return;
        }
        setBooks(items);
        setSelectedBookId((prev) => prev || items[0]?.id || "");
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setUiError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setBooksLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedBookId) {
      setChapters([]);
      setSelectedChapterIndex(null);
      setChapterDetail(null);
      return;
    }

    let cancelled = false;
    setChaptersLoading(true);
    listChapters(selectedBookId)
      .then((items) => {
        if (cancelled) {
          return;
        }
        setChapters(items);
        setSelectedChapterIndex((prev) => {
          if (prev && items.some((item) => item.chapter_index === prev)) {
            return prev;
          }
          return items[0]?.chapter_index ?? null;
        });
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setUiError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setChaptersLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedBookId]);

  useEffect(() => {
    if (!selectedBookId || selectedChapterIndex === null) {
      setChapterDetail(null);
      return;
    }

    let cancelled = false;
    setChapterLoading(true);
    getChapter(selectedBookId, selectedChapterIndex)
      .then((chapter) => {
        if (!cancelled) {
          setChapterDetail(chapter);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setUiError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setChapterLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedBookId, selectedChapterIndex]);

  useEffect(() => {
    if (!selectedBookId) {
      setCharacters([]);
      setSelectedCharacterId("");
      setCharacterDetail(null);
      return;
    }

    let cancelled = false;
    setCharactersLoading(true);
    listCharacters(selectedBookId)
      .then((items) => {
        if (cancelled) {
          return;
        }
        setCharacters(items);
        setSelectedCharacterId((prev) => {
          if (prev && items.some((item) => item.id === prev)) {
            return prev;
          }
          return items[0]?.id || "";
        });
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setUiError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setCharactersLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedBookId]);

  useEffect(() => {
    if (!selectedBookId || !selectedCharacterId) {
      setCharacterDetail(null);
      return;
    }

    let cancelled = false;
    setCharacterLoading(true);
    getCharacterDetail(selectedBookId, selectedCharacterId)
      .then((detail) => {
        if (!cancelled) {
          setCharacterDetail(detail);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setUiError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setCharacterLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedBookId, selectedCharacterId]);

  useEffect(() => {
    if (!selectedBookId || !selectedCharacterId) {
      setCharacterPortrait(null);
      return;
    }

    let cancelled = false;
    setPortraitLoading(true);
    listCharacterPortraits(selectedBookId, undefined, selectedCharacterId)
      .then((items) => {
        if (!cancelled) {
          setCharacterPortrait(items[0] || null);
          setPortraitImageFailed(false);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setUiError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setPortraitLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedBookId, selectedCharacterId]);

  useEffect(() => {
    if (!selectedBookId || !selectedCharacterId || !characterDetail) {
      return;
    }
    if (portraitLoading || portraitGenerating) {
      return;
    }

    const shouldGenerate =
      !characterPortrait ||
      characterPortrait.status === "failed" ||
      (!characterPortrait.image_url && characterPortrait.status !== "generating");

    if (!shouldGenerate) {
      return;
    }

    let cancelled = false;
    setPortraitGenerating(true);
    triggerCharacterPortraitGenerate(selectedBookId, selectedCharacterId)
      .then((resp) => {
        if (cancelled) {
          return;
        }
        const pendingTask: TaskStatusResponse = {
          task_id: resp.task_id,
          status: "PENDING",
          result: { book_id: resp.book_id, status: resp.status }
        };
        setTaskInfo(pendingTask);
        setTaskMessage(`已为角色 ${characterDetail.canonical_name} 提交立绘生成任务`);
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setUiError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setPortraitGenerating(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    selectedBookId,
    selectedCharacterId,
    characterDetail,
    characterPortrait,
    portraitGenerating,
    portraitLoading
  ]);

  useEffect(() => {
    if (!taskInfo || taskInfo.status === "SUCCESS" || taskInfo.status === "FAILURE") {
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const latest = await getTaskStatus(taskInfo.task_id);
        if (cancelled) {
          return;
        }
        setTaskInfo(latest);
        setTaskMessage(normalizeTaskMessage(latest));

        if (latest.status === "SUCCESS") {
          const refreshedBooks = await listBooks();
          if (cancelled) {
            return;
          }
          setBooks(refreshedBooks);
          if (selectedBookId) {
            const refreshedCharacters = await listCharacters(selectedBookId);
            if (!cancelled) {
              setCharacters(refreshedCharacters);
            }
            if (selectedCharacterId) {
              const refreshedPortraits = await listCharacterPortraits(
                selectedBookId,
                undefined,
                selectedCharacterId
              );
              if (!cancelled) {
                setCharacterPortrait(refreshedPortraits[0] || null);
              }
            }
          }
        } else if (selectedBookId && selectedCharacterId) {
          const refreshedPortraits = await listCharacterPortraits(
            selectedBookId,
            undefined,
            selectedCharacterId
          );
          if (!cancelled) {
            setCharacterPortrait(refreshedPortraits[0] || null);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setUiError((err as Error).message);
        }
      }
    }, TASK_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [taskInfo, selectedBookId, selectedCharacterId]);

  useEffect(() => {
    if (characterDetail?.canonical_name) {
      setChatRoleName(characterDetail.canonical_name);
    }
  }, [characterDetail?.id]);

  useEffect(() => {
    setChatMessages([]);
    setChatSessionId("");
    setChatInput("");
    setChatRoleName("Narrator");
  }, [selectedBookId]);

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setUiError("");

    if (!uploadFile) {
      setUiError("请先选择一个 .txt 文件");
      return;
    }
    if (!uploadFile.name.toLowerCase().endsWith(".txt")) {
      setUiError("目前仅支持 .txt 文件");
      return;
    }

    setUploading(true);
    try {
      const response = await uploadBookTxt(uploadFile, uploadTitle);
      const pendingTask: TaskStatusResponse = {
        task_id: response.task_id,
        status: "PENDING",
        result: { book_id: response.book_id, status: response.status }
      };
      setTaskInfo(pendingTask);
      setTaskMessage("上传成功，开始切章任务...");
      setUploadFile(null);
      setUploadTitle("");
      setSelectedBookId(response.book_id);
    } catch (err) {
      setUiError((err as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const handleSyncSkillsToCurrentChapter = async () => {
    if (!selectedBookId) {
      setUiError("请先选择一本书");
      return;
    }
    if (selectedChapterIndex === null) {
      setUiError("请先选择章节");
      return;
    }

    setUiError("");
    setSyncingSkills(true);
    try {
      const resp = await runBookSkills(selectedBookId, selectedChapterIndex, true);
      const pendingTask: TaskStatusResponse = {
        task_id: resp.task_id,
        status: "PENDING",
        result: { book_id: resp.book_id, status: resp.status }
      };
      setTaskInfo(pendingTask);
      setTaskMessage(`已提交技能增量任务，目标章节：${selectedChapterIndex}`);
    } catch (err) {
      setUiError((err as Error).message);
    } finally {
      setSyncingSkills(false);
    }
  };

  const handleSendChat = async () => {
    const message = chatInput.trim();
    if (!message || chatLoading) {
      return;
    }
    if (!selectedBookId) {
      setUiError("请先选择一本书");
      return;
    }

    const userMessage: ChatMessage = {
      id: makeMessageId("u"),
      role: "user",
      text: message
    };
    setChatMessages((prev) => [...prev, userMessage]);
    setChatInput("");
    setChatLoading(true);

    try {
      const resp = await postRoleChat({
        book_id: selectedBookId,
        role_name: chatRoleName,
        message,
        chapter_index: selectedChapterIndex,
        session_id: chatSessionId || undefined
      });
      if (resp.session_id) {
        setChatSessionId(resp.session_id);
      }

      const assistantMessage: ChatMessage = {
        id: makeMessageId("a"),
        role: "assistant",
        text: resp.answer,
        meta: buildAssistantMeta({
          spoilerRisk: resp.spoiler_risk,
          guardApplied: resp.guard_applied,
          llmUsed: resp.llm_used,
          llmModel: resp.llm_model,
          llmError: resp.llm_error
        }),
        citations: resp.citations || []
      };
      setChatMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      const errorMessage: ChatMessage = {
        id: makeMessageId("a"),
        role: "assistant",
        text: `聊天请求失败：${(err as Error).message}`
      };
      setChatMessages((prev) => [...prev, errorMessage]);
    } finally {
      setChatLoading(false);
    }
  };

  const handleChatKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSendChat();
    }
  };

  return (
    <main className="workspace">
      <header className="topbar">
        <div>
          <h1>StoryVerse 阅读工作台</h1>
          <p>上传文本、自动切章、查看角色卡，并和已出场角色进行无剧透对话。</p>
        </div>
        <div className="health-box">
          <span>API: {API_BASE_URL}</span>
          <strong data-state={health}>{health}</strong>
          {healthError ? <em>{healthError}</em> : null}
        </div>
      </header>

      <section className="layout">
        <aside className="sidebar">
          <article className="panel">
            <h2>导入书籍</h2>
            <form className="upload-form" onSubmit={handleUpload}>
              <label htmlFor="book-title">书名（可选）</label>
              <input
                id="book-title"
                placeholder="例如：红楼梦"
                value={uploadTitle}
                onChange={(event) => setUploadTitle(event.target.value)}
              />

              <label htmlFor="book-file">TXT 文件</label>
              <input
                id="book-file"
                type="file"
                accept=".txt,text/plain"
                onChange={(event) => setUploadFile(event.target.files?.[0] || null)}
              />
              <button type="submit" disabled={uploading}>
                {uploading ? "上传中..." : "上传并切章"}
              </button>
            </form>

            {taskInfo ? (
              <div className="task-box">
                <p>
                  任务状态：<strong>{taskInfo.status}</strong>
                </p>
                <p>{taskMessage || normalizeTaskMessage(taskInfo)}</p>
                <p className="muted">task_id: {taskInfo.task_id}</p>
              </div>
            ) : null}

            {uiError ? <p className="error">{uiError}</p> : null}
          </article>

          <article className="panel">
            <h2>书籍列表</h2>
            {booksLoading ? <p className="muted">加载中...</p> : null}
            <ul className="book-list">
              {books.map((book) => (
                <li key={book.id}>
                  <button
                    className={book.id === selectedBookId ? "active" : ""}
                    onClick={() => setSelectedBookId(book.id)}
                    type="button"
                  >
                    <span className="title">{book.title}</span>
                    <span className={`status status-${book.status}`}>{book.status}</span>
                    <span className="time">{formatDate(book.created_at)}</span>
                    <span className="muted">checkpoint: {book.skill_checkpoint_chapter ?? 0}</span>
                  </button>
                </li>
              ))}
            </ul>
          </article>

          <article className="panel">
            <h2>章节目录</h2>
            {!selectedBook ? <p className="muted">请先选择一本书。</p> : null}
            {selectedBook && chaptersLoading ? <p className="muted">章节加载中...</p> : null}
            <ul className="chapter-list">
              {chapters.map((chapter) => (
                <li key={chapter.id}>
                  <button
                    className={chapter.chapter_index === selectedChapterIndex ? "active" : ""}
                    type="button"
                    onClick={() => setSelectedChapterIndex(chapter.chapter_index)}
                  >
                    <span className="index">#{chapter.chapter_index}</span>
                    <span className="title">{chapter.title}</span>
                  </button>
                </li>
              ))}
            </ul>
          </article>

          <article className="panel">
            <h2>角色模块</h2>
            {!selectedBook ? <p className="muted">请先选择一本书。</p> : null}
            {selectedBook && charactersLoading ? <p className="muted">角色加载中...</p> : null}
            <ul className="character-list">
              {characters.map((character) => (
                <li key={character.id}>
                  <button
                    className={character.id === selectedCharacterId ? "active" : ""}
                    type="button"
                    onClick={() => setSelectedCharacterId(character.id)}
                  >
                    <span className="title">{character.canonical_name}</span>
                    <span className="meta">
                      提及 {character.mention_count} · 置信 {character.confidence.toFixed(2)}
                    </span>
                    {character.aliases.length ? (
                      <span className="muted alias-line">
                        别名：{character.aliases.slice(0, 3).join(" / ")}
                      </span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          </article>
        </aside>

        <article className="reader panel">
          {!selectedBook ? <h2>选择一本书开始阅读</h2> : null}
          {selectedBook ? (
            <>
              <div className="reader-head">
                <h2>{selectedBook.title}</h2>
                <p>
                  状态：<strong>{selectedBook.status}</strong>，共 {chapters.length} 章
                </p>
                <button
                  type="button"
                  className="sync-skill-btn"
                  onClick={() => void handleSyncSkillsToCurrentChapter()}
                  disabled={syncingSkills || selectedChapterIndex === null}
                >
                  {syncingSkills ? "提交中..." : `同步技能到第 ${selectedChapterIndex ?? "?"} 章`}
                </button>
              </div>

              {chapterLoading ? <p className="muted">正文加载中...</p> : null}
              {!chapterLoading && chapterDetail ? (
                <section className="chapter-content">
                  <h3>
                    第 {chapterDetail.chapter_index} 章 · {chapterDetail.title}
                  </h3>
                  <pre>{chapterDetail.raw_text}</pre>
                </section>
              ) : null}

              <section className="character-detail">
                <h3>角色详情</h3>
                {characterLoading ? <p className="muted">角色详情加载中...</p> : null}
                {!characterLoading && !characterDetail ? (
                  <p className="muted">从左侧选择角色查看人格卡与状态。</p>
                ) : null}
                {!characterLoading && characterDetail ? (
                  <div className="character-card-grid">
                    <article className="character-card">
                      <h4>{characterDetail.canonical_name}</h4>
                      <p className="muted">
                        首现章节：{characterDetail.first_chapter_index ?? "未知"} · 提及：
                        {characterDetail.mention_count}
                      </p>
                      {characterDetail.card ? (
                        <>
                          <p>
                            <strong>身份：</strong>
                            {characterDetail.card.identity_summary}
                          </p>
                          <p>
                            <strong>性格：</strong>
                            {characterDetail.card.personality_summary}
                          </p>
                          <p>
                            <strong>说话风格：</strong>
                            {characterDetail.card.speaking_style}
                          </p>
                          <p>
                            <strong>价值与禁忌：</strong>
                            {characterDetail.card.values_and_taboo}
                          </p>
                        </>
                      ) : (
                        <p className="muted">暂无角色卡。</p>
                      )}
                    </article>

                    <article className="character-card">
                      <h4>进度状态</h4>
                      {characterDetail.latest_state ? (
                        <>
                          <p>
                            <strong>状态章节：</strong>第 {characterDetail.latest_state.chapter_index} 章
                          </p>
                          <p>
                            <strong>情绪：</strong>
                            {characterDetail.latest_state.emotional_state}
                          </p>
                          <p>
                            <strong>立场：</strong>
                            {characterDetail.latest_state.stance}
                          </p>
                          <p>
                            <strong>目标：</strong>
                            {characterDetail.latest_state.current_goal}
                          </p>
                          <p>
                            <strong>关系快照：</strong>
                            {characterDetail.latest_state.relation_snapshot}
                          </p>
                        </>
                      ) : (
                        <p className="muted">暂无状态快照。</p>
                      )}

                      <h4>证据片段</h4>
                      <ul className="evidence-list">
                        {characterDetail.evidences.slice(0, 5).map((item, idx) => (
                          <li key={`${item.chapter_index}-${idx}`}>
                            <span className="muted">第 {item.chapter_index} 章：</span>
                            {item.excerpt}
                          </li>
                        ))}
                      </ul>
                    </article>

                    <article className="character-card portrait-card-wrap">
                      <h4>人物立绘</h4>
                      {portraitLoading ? <p className="muted">立绘加载中...</p> : null}
                      {!portraitLoading && portraitGenerating ? (
                        <p className="muted">正在根据人物性格与外貌证据生成立绘...</p>
                      ) : null}
                      {!portraitLoading && !characterPortrait ? (
                        <p className="muted">当前角色暂无立绘，请先同步技能到角色已出场章节。</p>
                      ) : null}
                      {!portraitLoading && characterPortrait ? (
                        <>
                          <div className="portrait-status-line">
                            <span
                              className={`status-chip status-${characterPortrait.status}`}
                              title={characterPortrait.status}
                            >
                              {formatPortraitStatus(characterPortrait.status)}
                            </span>
                            <span className="muted">
                              解锁章节：第 {characterPortrait.unlocked_chapter_index} 章
                            </span>
                          </div>
                          {characterPortrait.image_url ? (
                            <div className="portrait-media">
                              <img
                                src={buildProxyImageUrl(characterPortrait.image_url)}
                                alt={`${characterPortrait.canonical_name} 立绘`}
                                onError={() => setPortraitImageFailed(true)}
                              />
                            </div>
                          ) : (
                            <div className="portrait-placeholder">等待出图结果...</div>
                          )}
                          {portraitImageFailed ? (
                            <p className="error">
                              图片加载失败，请检查网络；可直接打开：
                              <a
                                href={buildProxyImageUrl(characterPortrait.image_url)}
                                target="_blank"
                                rel="noreferrer"
                              >
                                立绘链接
                              </a>
                            </p>
                          ) : null}
                        </>
                      ) : null}
                    </article>
                  </div>
                ) : null}
              </section>

              <section className="chat-panel">
                <div className="chat-head">
                  <h3>角色对话</h3>
                  <div className="chat-controls">
                    <label htmlFor="chat-role">扮演角色</label>
                    <select
                      id="chat-role"
                      value={chatRoleName}
                      onChange={(event) => setChatRoleName(event.target.value)}
                    >
                      {roleOptions.map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                    </select>
                    <span className="muted">
                      当前进度：第 {selectedChapterIndex ?? "?"} 章（用于防剧透）
                    </span>
                  </div>
                </div>

                <div className="chat-messages">
                  {chatMessages.length === 0 ? (
                    <p className="muted">
                      这里可以直接与角色对话。系统会按你当前章节做证据检索，并进行防剧透约束。
                    </p>
                  ) : null}
                  {chatMessages.map((msg) => (
                    <article key={msg.id} className={`chat-message chat-${msg.role}`}>
                      <header>
                        <strong>{msg.role === "user" ? "你" : chatRoleName}</strong>
                      </header>
                      <p>{msg.text}</p>
                      {msg.meta ? <div className="chat-meta">{msg.meta}</div> : null}
                      {msg.citations && msg.citations.length > 0 ? (
                        <ul className="citation-list">
                          {msg.citations.slice(0, 3).map((c, idx) => (
                            <li key={`${msg.id}-c-${idx}`}>
                              第 {c.chapter_index} 章《{c.chapter_title}》 · 相似度 {c.score.toFixed(3)}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </article>
                  ))}
                </div>

                <div className="chat-input-box">
                  <textarea
                    value={chatInput}
                    onChange={(event) => setChatInput(event.target.value)}
                    onKeyDown={handleChatKeyDown}
                    placeholder="输入你想对角色说的话。按 Enter 发送，Shift+Enter 换行。"
                    rows={4}
                    disabled={chatLoading || !selectedBookId}
                  />
                  <button type="button" onClick={() => void handleSendChat()} disabled={chatLoading || !chatInput.trim()}>
                    {chatLoading ? "发送中..." : "发送"}
                  </button>
                </div>
              </section>
            </>
          ) : null}
        </article>
      </section>
    </main>
  );
}
