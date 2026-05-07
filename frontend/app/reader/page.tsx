import Link from "next/link";

export default function ReaderEntryPage() {
  return (
    <main className="landing">
      <section className="landing-hero">
        <article className="landing-copy">
          <p className="eyebrow">Reader Entrance</p>
          <h1>阅读入口需要先选择一本书</h1>
          <p>
            当前阅读页采用动态路由：<code>/reader/[bookId]</code>。先从书库进入，
            系统会自动带上书籍 ID 并打开沉浸式阅读 + 右侧人物对话页面。
          </p>
          <div className="landing-actions">
            <Link href="/library" className="btn-primary">
              前往书库选书
            </Link>
            <Link href="/" className="btn-ghost">
              返回首页
            </Link>
          </div>
        </article>

        <article className="landing-card">
          <h3>正确访问方式</h3>
          <ul>
            <li>从“书库”点击“阅读”按钮</li>
            <li>或直接访问 `/reader/&lt;bookId&gt;`</li>
            <li>示例：`/reader/bf3ede4a-2f74-4248-b853-f83cc2dae339`</li>
          </ul>
        </article>
      </section>
    </main>
  );
}

