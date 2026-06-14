import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';

interface NavItem {
  label: string;
  href: string;
}

const NAV_ITEMS: NavItem[] = [
  { label: '仪表盘', href: '/admin' },
  { label: '职位管理', href: '/admin/jobs' },
  { label: '题库管理', href: '/admin/questions' },
  { label: '候选人', href: '/admin/candidates' },
  { label: '面试记录', href: '/admin/records' },
  { label: '设置', href: '/admin/settings' },
];

interface AdminShellProps {
  active: string;
  children: ReactNode;
}

export default function AdminShell({ active, children }: AdminShellProps) {
  return (
    <div className="flex min-h-full bg-bg">
      {/* ── Desktop sidebar (fixed left, hidden on small screens) ── */}
      <aside className="hidden md:flex md:flex-col md:fixed md:inset-y-0 md:left-0 md:w-56 lg:w-64 bg-surface border-r border-border z-20">
        {/* Brand */}
        <div className="px-5 py-6 border-b border-border">
          <span className="text-base font-semibold text-text leading-tight block">
            菜鸟庆面试
          </span>
          <span className="text-xs text-muted mt-0.5 block">HR 管理平台</span>
        </div>

        {/* Nav links */}
        <nav className="flex-1 px-3 py-4 flex flex-col gap-0.5" aria-label="管理导航">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.href} item={item} active={active} />
          ))}
        </nav>

        {/* Bottom user badge */}
        <div className="px-4 py-4 border-t border-border">
          <div className="flex items-center gap-3">
            <div
              className="w-8 h-8 rounded-full bg-surface2 border border-border flex items-center justify-center text-cyan text-xs font-bold"
              aria-hidden="true"
            >
              HR
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium text-text truncate">HR · 菜鸟庆</p>
              <p className="text-[11px] text-muted truncate">管理员</p>
            </div>
          </div>
        </div>
      </aside>

      {/* ── Mobile top bar (visible on small screens) ── */}
      <header className="md:hidden fixed top-0 inset-x-0 z-20 bg-surface border-b border-border">
        <div className="px-4 py-3 flex items-center justify-between">
          <span className="text-sm font-semibold text-text">菜鸟庆面试</span>
          <span className="text-xs text-muted">HR 管理平台</span>
        </div>
        {/* Horizontal scrollable nav */}
        <nav
          className="flex overflow-x-auto scrollbar-hide gap-1 px-3 pb-2"
          aria-label="管理导航"
          style={{ WebkitOverflowScrolling: 'touch' }}
        >
          {NAV_ITEMS.map((item) => (
            <MobileNavLink key={item.href} item={item} active={active} />
          ))}
        </nav>
      </header>

      {/* ── Main content area ── */}
      <main className="flex-1 md:ml-56 lg:ml-64 pt-[88px] md:pt-0 min-h-full">
        <div className="p-4 md:p-8">
          {children}
        </div>
      </main>
    </div>
  );
}

function NavLink({ item, active }: { item: NavItem; active: string }) {
  const isActive = active === item.label;
  return (
    <Link
      to={item.href}
      className={[
        'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors duration-150',
        isActive
          ? 'bg-surface2 text-text font-medium'
          : 'text-muted hover:text-text hover:bg-surface2/50',
      ].join(' ')}
      aria-current={isActive ? 'page' : undefined}
    >
      {isActive && (
        <span
          className="w-1.5 h-1.5 rounded-full bg-cyan flex-shrink-0"
          aria-hidden="true"
        />
      )}
      {!isActive && <span className="w-1.5 h-1.5 flex-shrink-0" aria-hidden="true" />}
      {item.label}
    </Link>
  );
}

function MobileNavLink({ item, active }: { item: NavItem; active: string }) {
  const isActive = active === item.label;
  return (
    <Link
      to={item.href}
      className={[
        'flex-shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors duration-150 whitespace-nowrap',
        isActive
          ? 'bg-surface2 text-cyan'
          : 'text-muted hover:text-text',
      ].join(' ')}
      aria-current={isActive ? 'page' : undefined}
    >
      {item.label}
    </Link>
  );
}
