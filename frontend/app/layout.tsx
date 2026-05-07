import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "StoryVerse Agent",
  description: "Immersive reading app powered by multi-agents"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
