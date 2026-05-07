"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import {
  API_BASE_URL,
  Book,
  TaskStatusResponse,
  getTaskStatus,
  listBooks,
  uploadBookTxt,
} from "@/lib/api";
import { StoryShell } from "../components/StoryShell";

export default function LibraryPage() {
  const [books, setBooks] = useState<Book[]>([]);
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [task, setTask] = useState<TaskStatusResponse | null>(null);

  const refreshBooks = async () => {
    const data = await listBooks();
    setBooks(data);
  };

  useEffect(() => {
    refreshBooks().catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!task || task.status === "SUCCESS" || task.status === "FAILURE") return;
    const timer = window.setTimeout(async () => {
      try {
        const latest = await getTaskStatus(task.task_id);
        setTask(latest);
        if (latest.status === "SUCCESS") {
          await refreshBooks();
        }
      } catch (e) {
        setError((e as Error).message);
      }
    }, 1800);
    return () => window.clearTimeout(timer);
  }, [task]);

  const handleUpload = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const created = await uploadBookTxt(file, title || undefined);
      setTask({ task_id: created.task_id, status: "PENDING" });
      setTitle("");
      setFile(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <StoryShell
      title="书库与导入"
      subtitle="先选一本书，开始沉浸阅读"
      nav={[
        { href: "/", label: "首页" },
        { href: "/library", label: "书库" },
      ]}
    >
      <section className="paper-grid">
        <article className="paper-card">
          <h2>导入小说</h2>
          <form className="form-stack" onSubmit={handleUpload}>
            <label>
              书名
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="例如：红楼梦"
              />
            </label>
            <label>
              文件（txt）
              <input
                type="file"
                accept=".txt,text/plain"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
            <button type="submit" className="btn-primary" disabled={!file || uploading}>
              {uploading ? "上传中..." : "上传并构建"}
            </button>
          </form>
          {task ? (
            <div className="hint-box">
              <div>任务ID：{task.task_id}</div>
              <div>状态：{task.status}</div>
            </div>
          ) : null}
          {error ? <p className="error">{error}</p> : null}
          <p className="muted">API: {API_BASE_URL}</p>
        </article>

        <article className="paper-card wide">
          <h2>已导入书籍</h2>
          <ul className="book-table">
            {books.map((book) => (
              <li key={book.id}>
                <div>
                  <strong>{book.title}</strong>
                  <p className="muted">状态：{book.status}</p>
                </div>
                <div className="row-actions">
                  <Link href={`/reader/${book.id}`} className="btn-ghost">阅读</Link>
                  <Link href={`/chat/${book.id}`} className="btn-ghost">对话</Link>
                  <Link href={`/visual/${book.id}`} className="btn-ghost">立绘</Link>
                </div>
              </li>
            ))}
          </ul>
        </article>
      </section>
    </StoryShell>
  );
}

