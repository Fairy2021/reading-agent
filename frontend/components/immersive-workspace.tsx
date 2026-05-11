"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Book,
  ChapterDetail,
  ChapterSummary,
  CharacterSummary,
  ChatResponse,
  MediaAsset,
  resolveAssetUrl,
  getChapter,
  listBooks,
  bootstrapTopPortraits,
  listChapters,
  listCharacters,
  listMediaAssets,
  enqueueVisualPortraitJob,
  getVisualJobStatus,
  postRoleChat,
} from "@/lib/api";
import { useReaderStore } from "@/lib/store";
import { AmbientParticles, CandlelightGlow } from "@/components/ambient-particles";
import { AncientBookReader } from "@/components/ancient-book-reader";
import { BookCollectionPanel } from "@/components/book-collection-panel";
import { CharacterCompanionPanel } from "@/components/character-companion-panel";

type ImmersiveWorkspaceProps = {
  initialBookId?: string;
  initialPanel?: "book" | "reader" | "chat";
};

export function ImmersiveWorkspace({ initialBookId, initialPanel = "reader" }: ImmersiveWorkspaceProps) {
  const {
    currentBookId,
    currentChapter,
    activeCharacter,
    setCurrentBookId,
    setCurrentChapter,
    setActiveCharacter,
    getConversation,
    setConversationSessionId,
    pushConversationMessage,
    recordUserUtterance,
    getAffinity,
  } = useReaderStore();

  const [books, setBooks] = useState<Book[]>([]);
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [chapter, setChapter] = useState<ChapterDetail | null>(null);
  const [characters, setCharacters] = useState<CharacterSummary[]>([]);
  const [portraitByCharacterId, setPortraitByCharacterId] = useState<Record<string, string>>({});
  const [activePortrait, setActivePortrait] = useState<MediaAsset | null>(null);
  const [message, setMessage] = useState("");
  const [loadingBooks, setLoadingBooks] = useState(false);
  const [loadingChapter, setLoadingChapter] = useState(false);
  const [loadingChat, setLoadingChat] = useState(false);
  const [error, setError] = useState("");
  const [portraitJobLoading, setPortraitJobLoading] = useState(false);
  const [portraitJobStateByCharacterId, setPortraitJobStateByCharacterId] = useState<
    Record<string, { jobId: string; status: string; error?: string }>
  >({});
  void initialPanel;

  const roleOptions = useMemo(() => ["Narrator", ...characters.map((c) => c.canonical_name)], [characters]);
  const roleSelectOptions = useMemo(
    () => [
      { name: "Narrator", mentionCount: 0 },
      ...[...characters]
        .sort((a, b) => b.mention_count - a.mention_count)
        .map((c) => ({ name: c.canonical_name, mentionCount: c.mention_count })),
    ],
    [characters]
  );

  const chapterPos = useMemo(() => {
    if (!currentChapter) return -1;
    return chapters.findIndex((c) => c.chapter_index === currentChapter);
  }, [chapters, currentChapter]);

  const prevChapter = chapterPos > 0 ? chapters[chapterPos - 1] : null;
  const nextChapter = chapterPos >= 0 && chapterPos < chapters.length - 1 ? chapters[chapterPos + 1] : null;
  const activeSummary = useMemo(
    () => characters.find((c) => c.canonical_name === activeCharacter) || null,
    [characters, activeCharacter]
  );
  const activePortraitUrl = useMemo(() => {
    const fromDetail = resolveAssetUrl(activePortrait?.storage_url || "");
    if (fromDetail) return fromDetail;
    if (activeSummary?.id) return portraitByCharacterId[activeSummary.id] || null;
    return null;
  }, [activePortrait?.storage_url, activeSummary?.id, portraitByCharacterId]);
  const activeAffinity = getAffinity(currentBookId, activeCharacter);
  const activeConversation = getConversation(currentBookId, activeCharacter);
  const sessionId = activeConversation.sessionId;
  const messageHistory = activeConversation.messages;
  const unlockChapter = activeSummary?.first_chapter_index ?? null;
  const isUnlockedByChapter =
    activeCharacter !== "Narrator" &&
    !!unlockChapter &&
    !!currentChapter &&
    currentChapter >= unlockChapter;
  const canGeneratePortrait =
    activeCharacter !== "Narrator" &&
    !!currentBookId &&
    !!activeSummary &&
    isUnlockedByChapter &&
    activeAffinity >= 20;
  const portraitLockReason =
    activeCharacter === "Narrator"
      ? "旁白角色不支持立绘生成"
      : !unlockChapter || !currentChapter || currentChapter < unlockChapter
        ? `未解锁：需阅读至第 ${unlockChapter ?? "-"} 章`
        : activeAffinity < 20
          ? `好感度不足：当前 ${activeAffinity}/20（每对话 3 句 +20）`
          : "已解锁：可生成立绘";
  const activePortraitJobState = activeSummary?.id
    ? portraitJobStateByCharacterId[activeSummary.id]
    : undefined;
  const isPortraitGenerating =
    portraitJobLoading ||
    activePortraitJobState?.status === "queued" ||
    activePortraitJobState?.status === "running";
  const portraitStatusText = activePortraitJobState
    ? activePortraitJobState.status === "queued"
      ? "状态：排队中"
      : activePortraitJobState.status === "running"
        ? "状态：生成中"
        : activePortraitJobState.status === "completed"
          ? "状态：已完成"
          : activePortraitJobState.status === "failed"
            ? `状态：失败${activePortraitJobState.error ? `（${activePortraitJobState.error}）` : ""}`
            : `状态：${activePortraitJobState.status}`
    : "";

  useEffect(() => {
    setLoadingBooks(true);
    listBooks()
      .then((items) => {
        setBooks(items);
        if (initialBookId) {
          const matched = items.find((b) => b.id === initialBookId);
          if (matched) {
            setCurrentBookId(matched.id);
            return;
          }
        }
        if (!currentBookId && items[0]) setCurrentBookId(items[0].id);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoadingBooks(false));
  }, [currentBookId, initialBookId, setCurrentBookId]);

  useEffect(() => {
    if (!currentBookId) return;
    setError("");
    Promise.all([listChapters(currentBookId), listCharacters(currentBookId)])
      .then(([chs, chars]) => {
        setChapters(chs);
        setCharacters(chars);
        if (!currentChapter && chs[0]) setCurrentChapter(chs[0].chapter_index);
      })
      .catch((e: Error) => setError(e.message));
  }, [currentBookId, currentChapter, setCurrentChapter]);

  useEffect(() => {
    if (!currentBookId) {
      setPortraitByCharacterId({});
      return;
    }

    let mounted = true;
    const refreshPortraits = async () => {
      try {
        const assets = await listMediaAssets(currentBookId, "portrait");
        if (!mounted) return;
        const nextMap: Record<string, string> = {};
        for (const asset of assets) {
          if (!asset.character_id || !asset.storage_url) continue;
          if (!nextMap[asset.character_id]) {
            nextMap[asset.character_id] = resolveAssetUrl(asset.storage_url);
          }
        }
        setPortraitByCharacterId(nextMap);
      } catch {
        if (mounted) setPortraitByCharacterId({});
      }
    };

    refreshPortraits();
    bootstrapTopPortraits(currentBookId, 5).catch(() => {
      // Best-effort bootstrap only.
    });
    const timer = window.setInterval(refreshPortraits, 8000);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, [currentBookId]);

  useEffect(() => {
    if (!currentBookId || !currentChapter) return;
    setLoadingChapter(true);
    getChapter(currentBookId, currentChapter)
      .then(setChapter)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoadingChapter(false));
  }, [currentBookId, currentChapter]);

  useEffect(() => {
    if (!currentBookId || activeCharacter === "Narrator") {
      setActivePortrait(null);
      return;
    }
    const matched = characters.find((c) => c.canonical_name === activeCharacter);
    if (!matched) {
      setActivePortrait(null);
      return;
    }
    listMediaAssets(currentBookId, "portrait", matched.id)
      .then((items) => setActivePortrait(items[0] || null))
      .catch(() => setActivePortrait(null));
  }, [currentBookId, activeCharacter, characters]);

  const sendChat = async () => {
    if (!currentBookId || !currentChapter) return;
    const text = message.trim();
    if (!text) return;

    pushConversationMessage(currentBookId, activeCharacter, { role: "user", text });
    recordUserUtterance(currentBookId, activeCharacter);
    setMessage("");
    setLoadingChat(true);
    setError("");

    try {
      const resp: ChatResponse = await postRoleChat({
        book_id: currentBookId,
        role_name: activeCharacter,
        message: text,
        chapter_index: currentChapter,
        session_id: sessionId || undefined,
      });
      if (resp.session_id) {
        setConversationSessionId(currentBookId, activeCharacter, resp.session_id);
      }
      pushConversationMessage(currentBookId, activeCharacter, {
        role: "assistant",
        text: resp.answer,
        meta: `${resp.spoiler_risk} | model=${resp.llm_model || "n/a"}`,
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoadingChat(false);
    }
  };

  const handleGeneratePortrait = async () => {
    if (!currentBookId || !activeSummary || !canGeneratePortrait || portraitJobLoading) return;
    try {
      setPortraitJobLoading(true);
      setError("");
      const currentCharacterId = activeSummary.id;
      const enqueueResp = await enqueueVisualPortraitJob(
        currentBookId,
        currentCharacterId,
        undefined,
        currentChapter ?? undefined
      );
      setPortraitJobStateByCharacterId((s) => ({
        ...s,
        [currentCharacterId]: {
          jobId: enqueueResp.job_id,
          status: enqueueResp.status || "queued",
        },
      }));

      for (let i = 0; i < 120; i += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        const statusResp = await getVisualJobStatus(currentBookId, enqueueResp.job_id);
        const normalized =
          statusResp.status === "completed"
            ? "completed"
            : statusResp.status === "failed"
              ? "failed"
              : statusResp.status === "running"
                ? "running"
                : "queued";
        setPortraitJobStateByCharacterId((s) => ({
          ...s,
          [currentCharacterId]: {
            jobId: enqueueResp.job_id,
            status: normalized,
            error: statusResp.error_message || "",
          },
        }));

        if (normalized === "completed") {
          const assets = await listMediaAssets(currentBookId, "portrait", currentCharacterId);
          if (useReaderStore.getState().activeCharacter === activeSummary.canonical_name) {
            setActivePortrait(assets[0] || null);
          }
          break;
        }
        if (normalized === "failed") {
          break;
        }
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPortraitJobLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-screen overflow-x-hidden overflow-y-auto relative">
      <div className="absolute top-2 right-3 z-40 rounded-md border border-gold/40 bg-wood-dark/75 px-2 py-1 text-[10px] tracking-wider text-gold">
        UI V2
      </div>
      <CandlelightGlow />
      <AmbientParticles />

      <div className="absolute inset-0 z-0" style={{
        background: `
          radial-gradient(ellipse at 30% 20%, rgba(100,70,50,0.3) 0%, transparent 50%),
          radial-gradient(ellipse at 70% 80%, rgba(80,50,60,0.2) 0%, transparent 50%),
          linear-gradient(to bottom, #1a1410 0%, #120e0c 50%, #0d0a09 100%)
        `,
      }} />

      <div className="relative z-10 p-3 md:p-0 min-h-[100dvh] md:h-[100dvh] grid grid-cols-1 md:grid-cols-[250px_1fr_420px] xl:grid-cols-[300px_1fr_470px] gap-3 md:gap-0">
        <div className="h-[42dvh] md:h-full min-h-[300px]">
          <BookCollectionPanel
            books={books}
            loadingBooks={loadingBooks}
            selectedBookId={currentBookId}
            onSelectBook={(bookId) => {
              setCurrentBookId(bookId);
              setCurrentChapter(null);
            }}
            chapters={chapters}
            currentChapter={currentChapter}
            onSelectChapter={(idx) => {
              setCurrentChapter(idx);
            }}
            roleOptions={roleOptions}
            activeRole={activeCharacter}
            onSelectRole={setActiveCharacter}
            characters={characters}
            portraitByCharacterId={portraitByCharacterId}
            onSelectCharacter={(characterName) => {
              setActiveCharacter(characterName);
            }}
          />
        </div>

        <div className="h-[62dvh] md:h-full min-h-[420px] relative">
          <AncientBookReader
            chapter={chapter}
            chapterIndex={currentChapter}
            totalPages={Math.max(1, chapters.length)}
            loading={loadingChapter}
            onPrev={() => prevChapter && setCurrentChapter(prevChapter.chapter_index)}
            onNext={() => nextChapter && setCurrentChapter(nextChapter.chapter_index)}
            hasPrev={!!prevChapter}
            hasNext={!!nextChapter}
          />
        </div>

        <div className="h-[52dvh] md:h-full min-h-[360px] min-h-0">
          <CharacterCompanionPanel
            roleName={activeCharacter}
            roleOptions={roleSelectOptions}
            onChangeRole={setActiveCharacter}
            roleMeta={{
              firstChapter: activeSummary?.first_chapter_index ?? null,
              mentionCount: activeSummary?.mention_count ?? 0,
            }}
            portraitUrl={activePortraitUrl}
            messages={messageHistory}
            inputValue={message}
            onInputChange={setMessage}
            onSend={sendChat}
            isTyping={loadingChat}
            sessionId={sessionId}
            error={error}
            affinity={activeAffinity}
            canGeneratePortrait={canGeneratePortrait}
            generatingPortrait={isPortraitGenerating}
            portraitLockReason={portraitLockReason}
            portraitStatusText={portraitStatusText}
            onGeneratePortrait={handleGeneratePortrait}
          />
        </div>
      </div>
    </div>
  );
}

