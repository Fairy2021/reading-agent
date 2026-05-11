"use client";

import { motion } from "framer-motion";
import { BookOpen, Check } from "lucide-react";
import { Book, ChapterSummary, CharacterSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

type Props = {
  books: Book[];
  loadingBooks: boolean;
  selectedBookId: string | null;
  onSelectBook: (bookId: string) => void;
  chapters: ChapterSummary[];
  currentChapter: number | null;
  onSelectChapter: (chapter: number) => void;
  roleOptions: string[];
  activeRole: string;
  onSelectRole: (role: string) => void;
  characters: CharacterSummary[];
  portraitByCharacterId: Record<string, string>;
  onSelectCharacter: (characterName: string) => void;
};

export function BookCollectionPanel({
  books,
  loadingBooks,
  selectedBookId,
  onSelectBook,
  chapters,
  currentChapter,
  onSelectChapter,
  roleOptions,
  activeRole,
  onSelectRole,
  characters,
  portraitByCharacterId,
  onSelectCharacter,
}: Props) {
  const role = activeRole || "Narrator";
  const sortedCharacters = [...characters].sort((a, b) => b.mention_count - a.mention_count);
  const portraitCharacters = sortedCharacters.filter((c) => Boolean(portraitByCharacterId[c.id]));

  return (
    <div className="h-full min-h-0 flex flex-col bg-gradient-to-b from-wood-dark/95 to-wood-dark border-r border-gold/20 relative overflow-hidden">
      <div className="absolute inset-0 wood-texture opacity-30 pointer-events-none" />

      <div className="p-4 relative z-10">
        <div className="flex items-center gap-2 mb-4">
          <BookOpen className="w-5 h-5 text-gold" />
          <h2 className="text-gold font-serif text-lg tracking-wider">书籍收藏</h2>
          <span className="text-gold/50 text-xs ml-auto">BOOKS</span>
        </div>

        <div className="space-y-2 max-h-[34vh] overflow-y-auto pr-1 scroll-thin">
          {loadingBooks ? <div className="text-parchment/70 text-sm">加载书库中...</div> : null}
          {books.map((book, index) => (
            <motion.button
              key={book.id}
              onClick={() => onSelectBook(book.id)}
              className={cn(
                "w-full flex items-center gap-3 p-3 rounded-lg transition-all duration-300 border",
                selectedBookId === book.id
                  ? "bg-gold/15 border-gold/40"
                  : "bg-wood-medium/50 border-transparent hover:border-gold/25 hover:bg-wood-medium/70"
              )}
              whileHover={{ x: 4 }}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.05 }}
            >
              <div className="w-10 h-14 rounded-sm bg-gradient-to-br from-amber-900 to-amber-950 flex-shrink-0 relative overflow-hidden shadow-lg">
                <div className="absolute left-0 top-0 bottom-0 w-1 bg-black/20" />
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-parchment/80 text-[9px] font-bold writing-vertical">书</span>
                </div>
              </div>

              <div className="flex-1 text-left min-w-0">
                <div className="text-parchment font-serif text-sm truncate">{book.title}</div>
                <div className="text-parchment/50 text-xs">status: {book.status}</div>
              </div>
            </motion.button>
          ))}
        </div>
      </div>

      <div className="px-4"><div className="h-px bg-gradient-to-r from-transparent via-gold/30 to-transparent" /></div>

      <div className="p-4 relative z-10">
        <div className="flex items-center gap-2 mb-4">
          <h2 className="text-gold font-serif text-base tracking-wider">角色选择</h2>
          <span className="text-gold/50 text-xs ml-auto">ROLE</span>
        </div>
        <div className="rounded-lg border border-gold/30 bg-wood-medium/45 p-3">
          <label className="mb-2 block text-[11px] tracking-wider text-gold/70">当前对话角色</label>
          <select
            value={role}
            onChange={(e) => onSelectRole(e.target.value)}
            className="w-full rounded-md border border-gold/30 bg-wood-dark/70 px-3 py-2 text-sm text-parchment outline-none focus:border-gold/60"
          >
            <option value="Narrator">Narrator</option>
            {sortedCharacters.map((c) => (
              <option key={c.id} value={c.canonical_name}>
                {c.canonical_name}（{c.mention_count}）
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="px-4"><div className="h-px bg-gradient-to-r from-transparent via-gold/30 to-transparent" /></div>

      <div className="flex-1 min-h-0 p-4 overflow-hidden relative z-10 flex flex-col">
        <div className="flex items-center gap-2 mb-3 shrink-0">
          <h2 className="text-gold font-serif text-base tracking-wider">章节导航</h2>
          <span className="text-gold/50 text-xs ml-auto">CHAPTER</span>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden pr-1 space-y-1 scroll-thin touch-pan-y">
          {chapters.map((chapter) => (
            <button
              key={chapter.id}
              className={cn(
                "w-full flex items-center gap-3 p-3 rounded-lg transition-all duration-300 text-left border border-transparent",
                chapter.chapter_index === currentChapter ? "bg-crimson/20 border-crimson/40" : "hover:bg-wood-medium/50"
              )}
              onClick={() => onSelectChapter(chapter.chapter_index)}
            >
              <div className={cn(
                "w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0",
                chapter.chapter_index === currentChapter ? "bg-crimson/30 border border-crimson/50" : "bg-wood-light/30"
              )}>
                {chapter.chapter_index === currentChapter ? <div className="w-2 h-2 rounded-full bg-crimson animate-pulse" /> : <Check className="w-3 h-3 opacity-40" />}
              </div>
              <div className="flex-1 text-sm text-parchment/90 truncate">第 {chapter.chapter_index} 章</div>
            </button>
          ))}
        </div>
      </div>

      <div className="px-4"><div className="h-px bg-gradient-to-r from-transparent via-gold/30 to-transparent" /></div>

      <div className="p-4 relative z-10">
        <div className="flex items-center gap-2 mb-3">
          <h2 className="text-gold font-serif text-base tracking-wider">人物立绘入口</h2>
          <span className="text-gold/50 text-xs ml-auto">PORTRAITS</span>
        </div>
        <div className="space-y-2">
          {portraitCharacters.length > 0 ? (
            <>
              <select
                value={portraitCharacters.some((c) => c.canonical_name === activeRole) ? activeRole : portraitCharacters[0].canonical_name}
                onChange={(e) => onSelectCharacter(e.target.value)}
                className="w-full rounded-md border border-gold/30 bg-wood-dark/70 px-3 py-2 text-sm text-parchment outline-none focus:border-gold/60"
              >
                {portraitCharacters.map((c) => (
                  <option key={c.id} value={c.canonical_name}>
                    {c.canonical_name}（{c.mention_count}）
                  </option>
                ))}
              </select>
              {(() => {
                const current = portraitCharacters.find((c) => c.canonical_name === activeRole) || portraitCharacters[0];
                return (
                  <button
                    type="button"
                    onClick={() => onSelectCharacter(current.canonical_name)}
                    className="w-full flex items-center gap-2 rounded-lg border border-gold/30 bg-wood-medium/40 p-2"
                  >
                    <img
                      src={portraitByCharacterId[current.id]}
                      alt={current.canonical_name}
                      className="h-10 w-10 rounded object-cover border border-gold/30"
                    />
                    <span className="text-parchment text-sm truncate">
                      {current.canonical_name} · 提及 {current.mention_count}
                    </span>
                  </button>
                );
              })()}
            </>
          ) : (
            <div className="text-xs text-parchment/60">暂无可用立绘，先生成人物立绘后可点击切换。</div>
          )}
        </div>
      </div>
    </div>
  );
}
