"use client";

import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Heart, Send, Sparkles, Volume2 } from "lucide-react";
import { cn } from "@/lib/utils";

type ChatMessage = {
  role: "user" | "assistant";
  text: string;
  meta?: string;
};

type Props = {
  roleName: string;
  roleOptions: Array<{ name: string; mentionCount: number }>;
  onChangeRole: (role: string) => void;
  roleMeta?: {
    firstChapter?: number | null;
    mentionCount?: number;
  } | null;
  portraitUrl?: string | null;
  messages: ChatMessage[];
  inputValue: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  isTyping: boolean;
  sessionId: string | null;
  error: string;
  affinity: number;
  canGeneratePortrait: boolean;
  generatingPortrait: boolean;
  portraitLockReason: string;
  portraitStatusText?: string;
  onGeneratePortrait: () => void;
};

export function CharacterCompanionPanel({
  roleName,
  roleOptions,
  onChangeRole,
  roleMeta,
  portraitUrl,
  messages,
  inputValue,
  onInputChange,
  onSend,
  isTyping,
  sessionId,
  error,
  affinity,
  canGeneratePortrait,
  generatingPortrait,
  portraitLockReason,
  portraitStatusText,
  onGeneratePortrait,
}: Props) {
  const chatContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [messages, isTyping]);

  return (
    <div className="h-full flex flex-col bg-gradient-to-b from-wood-dark/90 via-purple-mist/10 to-wood-dark/95 border-l border-gold/20 relative overflow-hidden">
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-0 left-0 right-0 h-1/2 bg-gradient-to-b from-blossom/5 to-transparent" />
        <div className="absolute bottom-0 left-0 right-0 h-1/3 bg-gradient-to-t from-purple-mist/10 to-transparent" />
      </div>

      <div className="relative p-4 flex-shrink-0">
        <motion.div
          className="relative w-full h-[240px] rounded-lg overflow-hidden border-2 border-gold/30 bg-black/25"
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          <div className="absolute inset-0 bg-gradient-to-b from-blossom-soft/30 via-purple-mist/20 to-wood-dark/85" />
          {portraitUrl ? (
            <img
              src={portraitUrl}
              alt={roleName}
              className="absolute inset-0 h-full w-full object-contain"
            />
          ) : null}

          <div className="absolute bottom-0 left-0 right-0 h-[44%] bg-gradient-to-t from-wood-dark/85 to-transparent flex items-end justify-center">
            <div className="text-center pb-4">
              <div className="w-14 h-14 mx-auto rounded-full bg-gradient-to-br from-blossom/30 to-purple-mist/30 border-2 border-gold/30 flex items-center justify-center mb-1">
                <span className="text-gold text-lg font-serif">{roleName.slice(0, 1)}</span>
              </div>
              <motion.p className="text-parchment/90 text-sm font-serif italic" animate={{ opacity: [0.75, 1, 0.75] }} transition={{ duration: 2.5, repeat: Infinity }}>
                {roleName}
              </motion.p>
            </div>
          </div>
        </motion.div>

        <motion.div className="mt-2 flex items-center justify-between" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}>
          <div className="flex items-center gap-2">
            <h3 className="text-gold font-serif text-lg">{roleName}</h3>
            <button className="p-1.5 rounded-full bg-wood-medium/50 hover:bg-wood-medium text-gold/70 hover:text-gold transition-colors" type="button">
              <Volume2 className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-blossom/80 text-xs">Affinity</span>
            <div className="flex items-center gap-1.5">
              <Heart className="w-4 h-4 text-blossom fill-blossom/50" />
              <div className="w-20 h-2 bg-wood-dark rounded-full overflow-hidden">
                <motion.div
                  className="h-full bg-gradient-to-r from-blossom/70 to-blossom"
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.max(0, Math.min(100, affinity))}%` }}
                  transition={{ duration: 0.45 }}
                />
              </div>
              <span className="text-blossom text-xs font-mono w-8 text-right">{affinity}</span>
            </div>
          </div>
        </motion.div>

        <div className="mt-2">
          <select
            value={roleName}
            onChange={(e) => onChangeRole(e.target.value)}
            className="w-full rounded-md border border-gold/30 bg-wood-dark/70 px-3 py-2 text-sm text-parchment outline-none focus:border-gold/60"
          >
            {roleOptions.map((item) => (
              <option key={item.name} value={item.name}>
                {item.name}{item.name === "Narrator" ? "" : `（${item.mentionCount}）`}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="px-4"><div className="h-px bg-gradient-to-r from-transparent via-gold/30 to-transparent" /></div>

      <div className="px-4 pt-2">
        <div className="rounded-md border border-gold/20 bg-wood-medium/30 px-3 py-2 text-[12px] text-parchment/85 truncate">
          {roleName === "Narrator"
            ? "旁白模式：不绑定单一人物章节统计"
            : `出现章节：第 ${roleMeta?.firstChapter ?? "-"} 章 ｜ 提及次数：${roleMeta?.mentionCount ?? "-"}`}
        </div>

        {roleName !== "Narrator" ? (
          <div className="mt-2">
            <button
              type="button"
              onClick={onGeneratePortrait}
              disabled={!canGeneratePortrait || generatingPortrait}
              className={cn(
                "w-full rounded-md border px-3 py-2 text-sm transition-colors flex items-center justify-center gap-2",
                canGeneratePortrait && !generatingPortrait
                  ? "border-gold/55 bg-gold/15 text-gold hover:bg-gold/25"
                  : "border-gold/20 bg-wood-medium/20 text-parchment/45"
              )}
            >
              <Sparkles className="h-4 w-4" />
              {generatingPortrait ? "生成人物画像中..." : "生成人物画像"}
            </button>
            <p className="mt-1 text-[11px] text-parchment/60">{portraitLockReason}</p>
            {portraitStatusText ? (
              <p className="mt-1 text-[11px] text-gold/70">{portraitStatusText}</p>
            ) : null}
          </div>
        ) : null}
      </div>

      <div ref={chatContainerRef} className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3 relative z-10 scroll-thin">
        <AnimatePresence mode="popLayout">
          {messages.map((message, index) => (
            <motion.div key={`${message.role}-${index}`} initial={{ opacity: 0, y: 20, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }} transition={{ delay: index * 0.04 }} className={cn("flex", message.role === "user" ? "justify-end" : "justify-start")}>
              <div className={cn("max-w-[92%] rounded-lg p-3 relative", message.role === "user" ? "bg-gold/20 border border-gold/30 text-parchment" : "bg-wood-medium/60 border border-blossom/20 text-parchment/90")}>
                <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.text}</p>
                {message.meta ? <p className="mt-2 text-[10px] text-gold/60 italic border-t border-gold/10 pt-2">{message.meta}</p> : null}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        <AnimatePresence>
          {isTyping && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="flex justify-start">
              <div className="bg-wood-medium/60 border border-blossom/20 rounded-lg p-3">
                <div className="flex items-center gap-1">
                  {[0, 1, 2].map((i) => (
                    <motion.div key={i} className="w-2 h-2 rounded-full bg-blossom/50" animate={{ y: [0, -5, 0] }} transition={{ duration: 0.6, repeat: Infinity, delay: i * 0.2 }} />
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="p-4 border-t border-gold/10 relative z-10">
        <div className="flex items-center gap-2">
          <div className="flex-1 relative">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => onInputChange(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onSend()}
              placeholder="输入你想说的话..."
              className={cn("w-full bg-wood-medium/40 border border-gold/20 rounded-full", "px-4 py-2.5 text-sm text-parchment placeholder:text-parchment/30", "focus:outline-none focus:border-gold/40 focus:bg-wood-medium/60 transition-all duration-300")}
            />
          </div>

          <motion.button
            onClick={onSend}
            disabled={!inputValue.trim() || isTyping}
            className={cn("p-2.5 rounded-full transition-all", inputValue.trim() && !isTyping ? "bg-gold/20 text-gold hover:bg-gold/30" : "bg-wood-medium/30 text-parchment/30")}
            whileHover={inputValue.trim() && !isTyping ? { scale: 1.1 } : {}}
            whileTap={inputValue.trim() && !isTyping ? { scale: 0.95 } : {}}
          >
            <Send className="w-5 h-5" />
          </motion.button>
        </div>

        {sessionId ? <p className="mt-2 text-[11px] text-parchment/45">session: {sessionId}</p> : null}
        {error ? <p className="mt-2 text-[12px] text-red-300">{error}</p> : null}
      </div>
    </div>
  );
}
