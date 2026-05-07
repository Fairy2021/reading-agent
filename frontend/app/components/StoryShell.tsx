"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavItem = {
  href: string;
  label: string;
};

function NavLink({ href, label }: NavItem) {
  const pathname = usePathname();
  const active = pathname === href;
  return (
    <Link href={href} className={`side-link ${active ? "active" : ""}`}>
      {label}
    </Link>
  );
}

interface StoryShellProps {
  title: string;
  subtitle: string;
  nav: NavItem[];
  children: React.ReactNode;
}

export function StoryShell({ title, subtitle, nav, children }: StoryShellProps) {
  return (
    <main className="story-shell">
      <header className="story-topbar glass-panel">
        <div className="story-brand">
          <div className="brand-block brand-block-inline">
            <p className="brand-title">StoryVerse</p>
            <p className="brand-subtitle">{subtitle}</p>
          </div>
          <div className="story-page-meta">
            <span className="dream-chip">Multi-Agent</span>
            <span className="dream-chip">{title}</span>
          </div>
        </div>
        <nav className="story-top-nav">
          {nav.map((item) => (
            <NavLink key={item.href} href={item.href} label={item.label} />
          ))}
        </nav>
      </header>

      <section className="story-main">
        <header className="section-head">
          <h1>{title}</h1>
        </header>
        {children}
      </section>
    </main>
  );
}
