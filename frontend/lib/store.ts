import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

type ChatRow = { role: "user" | "assistant"; text: string; meta?: string };

type CharacterConversation = {
  sessionId: string | null;
  messages: ChatRow[];
};

type ReaderState = {
  currentBookId: string | null;
  currentChapter: number | null;
  activeCharacter: string;
  affinityByKey: Record<string, number>;
  utteranceCountByKey: Record<string, number>;
  conversationsByKey: Record<string, CharacterConversation>;
  setCurrentBookId: (bookId: string | null) => void;
  setCurrentChapter: (chapter: number | null) => void;
  setActiveCharacter: (role: string) => void;
  getConversation: (bookId: string | null, role: string) => CharacterConversation;
  setConversationSessionId: (bookId: string | null, role: string, id: string | null) => void;
  pushConversationMessage: (bookId: string | null, role: string, row: ChatRow) => void;
  clearBookConversations: (bookId: string | null) => void;
  recordUserUtterance: (bookId: string | null, role: string) => void;
  getAffinity: (bookId: string | null, role: string) => number;
};

function getAffinityKey(bookId: string | null, role: string): string {
  return `${bookId || "global"}::${role}`;
}

function getConversationKey(bookId: string | null, role: string): string {
  return `${bookId || "global"}::${role || "Narrator"}`;
}

const EMPTY_CONVERSATION: CharacterConversation = { sessionId: null, messages: [] };

export const useReaderStore = create<ReaderState>()(
  persist(
    (set, get) => ({
      currentBookId: null,
      currentChapter: null,
      activeCharacter: "Narrator",
      affinityByKey: {},
      utteranceCountByKey: {},
      conversationsByKey: {},
      setCurrentBookId: (bookId) => set({ currentBookId: bookId }),
      setCurrentChapter: (chapter) => set({ currentChapter: chapter }),
      setActiveCharacter: (role) => set({ activeCharacter: role }),
      getConversation: (bookId, role) => {
        const key = getConversationKey(bookId, role);
        return get().conversationsByKey[key] || EMPTY_CONVERSATION;
      },
      setConversationSessionId: (bookId, role, id) => {
        const key = getConversationKey(bookId, role);
        set((s) => ({
          conversationsByKey: {
            ...s.conversationsByKey,
            [key]: {
              sessionId: id,
              messages: s.conversationsByKey[key]?.messages || [],
            },
          },
        }));
      },
      pushConversationMessage: (bookId, role, row) => {
        const key = getConversationKey(bookId, role);
        set((s) => ({
          conversationsByKey: {
            ...s.conversationsByKey,
            [key]: {
              sessionId: s.conversationsByKey[key]?.sessionId || null,
              messages: [...(s.conversationsByKey[key]?.messages || []), row],
            },
          },
        }));
      },
      clearBookConversations: (bookId) => {
        const prefix = `${bookId || "global"}::`;
        set((s) => {
          const next = { ...s.conversationsByKey };
          for (const key of Object.keys(next)) {
            if (key.startsWith(prefix)) {
              delete next[key];
            }
          }
          return { conversationsByKey: next };
        });
      },
      recordUserUtterance: (bookId, role) => {
        if (!role || role === "Narrator") return;
        const key = getAffinityKey(bookId, role);
        const currentCount = get().utteranceCountByKey[key] || 0;
        const nextCount = currentCount + 1;
        const currentAffinity = get().affinityByKey[key] || 0;
        const shouldLevelUp = nextCount % 3 === 0;
        const nextAffinity = shouldLevelUp ? Math.min(100, currentAffinity + 20) : currentAffinity;

        set((s) => ({
          utteranceCountByKey: {
            ...s.utteranceCountByKey,
            [key]: nextCount,
          },
          affinityByKey: shouldLevelUp
            ? {
                ...s.affinityByKey,
                [key]: nextAffinity,
              }
            : s.affinityByKey,
        }));
      },
      getAffinity: (bookId, role) => {
        if (!role || role === "Narrator") return 0;
        const key = getAffinityKey(bookId, role);
        return get().affinityByKey[key] || 0;
      },
    }),
    {
      name: "storyverse-reader-store",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        affinityByKey: state.affinityByKey,
        utteranceCountByKey: state.utteranceCountByKey,
        conversationsByKey: state.conversationsByKey,
      }),
    }
  )
);
