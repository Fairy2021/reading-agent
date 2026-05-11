"use client";

import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight, List } from "lucide-react";
import { ChapterDetail } from "@/lib/api";
import { cn } from "@/lib/utils";

type Props = {
  chapter: ChapterDetail | null;
  chapterIndex: number | null;
  totalPages: number;
  loading: boolean;
  onPrev: () => void;
  onNext: () => void;
  hasPrev: boolean;
  hasNext: boolean;
};

export function AncientBookReader({
  chapter,
  chapterIndex,
  totalPages,
  loading,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
}: Props) {
  const leftText = loading ? "加载章节中..." : chapter?.raw_text || "";
  const rightText = chapter ? `标题：${chapter.title}\n\n阅读提示：可在右侧与角色同步对话，系统会按当前章节进度约束回答，避免剧透。` : "请选择一本书和章节开始阅读。";

  return (
    <div className="h-full flex flex-col p-4 lg:p-6 relative">
      <motion.div className="flex items-center justify-center gap-4 mb-3 lg:mb-4 shrink-0" initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
        <div className="h-px w-16 bg-gradient-to-r from-transparent to-gold/50" />
        <h1 className="text-gold font-serif text-xl lg:text-2xl tracking-[0.2em]">沉浸阅读</h1>
        <div className="text-parchment/50 text-xs lg:text-sm">|</div>
        <span className="text-parchment/70 text-xs lg:text-sm tracking-wider">Chapter {chapterIndex ?? "-"}</span>
        <div className="h-px w-16 bg-gradient-to-l from-transparent to-gold/50" />
      </motion.div>

      <motion.div className="relative flex-1 min-h-0 w-full" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.2, duration: 0.6 }}>
        <div className="absolute inset-x-4 bottom-0 h-10 bg-black/50 blur-2xl rounded-full" />
        <div className="absolute left-1/2 -translate-x-1/2 top-0 bottom-0 w-6 z-20 bg-gradient-to-r from-wood-dark via-wood-medium to-wood-dark shadow-lg" />
        <div className="absolute left-1/2 -translate-x-1/2 top-0 bottom-0 w-0.5 z-30 bg-gradient-to-b from-gold/30 via-gold/50 to-gold/30" />

        <div className={cn("absolute left-0 top-0 bottom-0 w-[calc(50%-4px)] rounded-l-lg overflow-hidden bg-gradient-to-br from-parchment to-parchment-dark shadow-[inset_-10px_0_20px_rgba(0,0,0,0.1)] border-l-4 border-t-2 border-b-2 border-wood-medium")}>
          <div className="absolute inset-0 parchment-texture" />
          <div className="relative h-full p-6 lg:p-8 flex flex-col">
            <h2 className="text-wood-dark font-serif text-lg lg:text-xl mb-4 text-center tracking-wider">{chapter?.title || "未选择章节"}</h2>
            <pre className="flex-1 overflow-auto whitespace-pre-wrap text-wood-dark/90 text-sm leading-relaxed font-serif scroll-thin">{leftText}</pre>
          </div>
        </div>

        <div className={cn("absolute right-0 top-0 bottom-0 w-[calc(50%-4px)] rounded-r-lg overflow-hidden bg-gradient-to-bl from-parchment to-parchment-dark shadow-[inset_10px_0_20px_rgba(0,0,0,0.1)] border-r-4 border-t-2 border-b-2 border-wood-medium")}>
          <div className="absolute inset-0 parchment-texture" />
          <div className="relative h-full p-6 lg:p-8 flex flex-col">
            <pre className="flex-1 overflow-auto whitespace-pre-wrap text-wood-dark/80 text-sm leading-relaxed scroll-thin">{rightText}</pre>
          </div>
        </div>
      </motion.div>

      <motion.div className="flex items-center justify-center gap-4 lg:gap-8 mt-3 lg:mt-4 shrink-0" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
        <button onClick={onPrev} disabled={!hasPrev} className="p-2 lg:p-3 rounded-full border border-gold/30 bg-wood-dark/50 hover:bg-wood-medium/50 disabled:opacity-30 disabled:cursor-not-allowed">
          <ChevronLeft className="w-4 h-4 lg:w-5 lg:h-5 text-gold" />
        </button>

        <div className="flex items-center gap-3 lg:gap-4">
          <div className="w-24 lg:w-32 h-1 bg-wood-dark rounded-full overflow-hidden">
            <div className="h-full bg-gradient-to-r from-gold/50 to-gold" style={{ width: `${Math.max(0, Math.min(100, ((chapterIndex || 0) / Math.max(1, totalPages)) * 100))}%` }} />
          </div>
          <span className="text-parchment/70 text-xs lg:text-sm font-mono">{chapterIndex || 0} / {totalPages}</span>
        </div>

        <button onClick={onNext} disabled={!hasNext} className="p-2 lg:p-3 rounded-full border border-gold/30 bg-wood-dark/50 hover:bg-wood-medium/50 disabled:opacity-30 disabled:cursor-not-allowed">
          <ChevronRight className="w-4 h-4 lg:w-5 lg:h-5 text-gold" />
        </button>

        <button className="p-2 lg:p-3 rounded-full border border-gold/30 bg-wood-dark/50 hover:bg-wood-medium/50">
          <List className="w-4 h-4 lg:w-5 lg:h-5 text-gold" />
        </button>
      </motion.div>
    </div>
  );
}
