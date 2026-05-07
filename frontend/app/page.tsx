import Link from "next/link";

export default function HomePage() {
  return (
    <main className="landing">
      <section className="landing-hero">
        <div className="landing-copy">
          <p className="eyebrow">StoryVerse</p>
          <h1>沉浸式名著阅读工作台</h1>
          <p>
            以人物角色对话、关系图谱与视觉场景为核心，
            用多智能体陪你读完整本书。
          </p>
          <div className="landing-actions">
            <Link href="/library" className="btn-primary">
              进入书库
            </Link>
            <Link href="/library" className="btn-ghost">
              上传并开始
            </Link>
          </div>
        </div>
        <div className="landing-card">
          <h3>工作区模块</h3>
          <ul>
            <li>书库与导入</li>
            <li>章节阅读</li>
            <li>角色对话</li>
            <li>立绘与场景图</li>
          </ul>
        </div>
      </section>
    </main>
  );
}
