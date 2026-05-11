import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "StoryVerse Immersive",
  description: "AI-native immersive reading frontend",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
