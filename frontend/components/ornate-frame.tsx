"use client";

import { cn } from "@/lib/utils";

interface OrnateFrameProps {
  children: React.ReactNode;
  className?: string;
  variant?: "default" | "elegant" | "subtle";
}

export function OrnateFrame({ children, className, variant = "default" }: OrnateFrameProps) {
  return (
    <div className={cn("relative", className)}>
      {/* Corner ornaments */}
      <CornerOrnament position="top-left" variant={variant} />
      <CornerOrnament position="top-right" variant={variant} />
      <CornerOrnament position="bottom-left" variant={variant} />
      <CornerOrnament position="bottom-right" variant={variant} />
      
      {/* Border lines */}
      <div className="absolute top-2 left-6 right-6 h-px bg-gradient-to-r from-transparent via-gold/50 to-transparent" />
      <div className="absolute bottom-2 left-6 right-6 h-px bg-gradient-to-r from-transparent via-gold/50 to-transparent" />
      <div className="absolute left-2 top-6 bottom-6 w-px bg-gradient-to-b from-transparent via-gold/50 to-transparent" />
      <div className="absolute right-2 top-6 bottom-6 w-px bg-gradient-to-b from-transparent via-gold/50 to-transparent" />
      
      {children}
    </div>
  );
}

function CornerOrnament({ 
  position, 
  variant 
}: { 
  position: "top-left" | "top-right" | "bottom-left" | "bottom-right";
  variant: "default" | "elegant" | "subtle";
}) {
  const positionClasses = {
    "top-left": "top-0 left-0",
    "top-right": "top-0 right-0 rotate-90",
    "bottom-left": "bottom-0 left-0 -rotate-90",
    "bottom-right": "bottom-0 right-0 rotate-180",
  };

  const sizeClasses = {
    default: "w-6 h-6",
    elegant: "w-8 h-8",
    subtle: "w-4 h-4",
  };

  return (
    <div className={cn("absolute", positionClasses[position], sizeClasses[variant])}>
      <svg viewBox="0 0 24 24" className="w-full h-full text-gold/60">
        <path
          d="M0 0 L24 0 L24 4 L4 4 L4 24 L0 24 Z"
          fill="currentColor"
        />
        <path
          d="M6 0 L8 0 L8 2 L6 2 Z M0 6 L2 6 L2 8 L0 8 Z"
          fill="currentColor"
          opacity="0.5"
        />
        <circle cx="4" cy="4" r="1.5" fill="currentColor" />
      </svg>
    </div>
  );
}

export function GoldenDivider({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2 py-2", className)}>
      <div className="flex-1 h-px bg-gradient-to-r from-transparent to-gold/40" />
      <svg viewBox="0 0 24 12" className="w-6 h-3 text-gold/50">
        <path
          d="M0 6 L8 2 L12 6 L16 2 L24 6 L16 10 L12 6 L8 10 Z"
          fill="currentColor"
        />
      </svg>
      <div className="flex-1 h-px bg-gradient-to-l from-transparent to-gold/40" />
    </div>
  );
}
