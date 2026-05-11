"use client";

import { useParams } from "next/navigation";
import { ImmersiveWorkspace } from "@/components/immersive-workspace";

export default function VisualByBookPage() {
  const params = useParams<{ bookId: string }>();
  return <ImmersiveWorkspace initialBookId={params.bookId} initialPanel="chat" />;
}
