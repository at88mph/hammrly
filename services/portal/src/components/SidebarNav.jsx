import { Link, useRouterState } from "@tanstack/react-router";

export function SidebarNav() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  const linkClass = (to) => {
    const active = pathname === to || (to !== "/" && pathname.startsWith(to));
    return active
      ? "block rounded-md bg-blue-50 px-3 py-2 text-sm font-medium text-portal-accent"
      : "block rounded-md px-3 py-2 text-sm text-slate-700 hover:bg-slate-100";
  };

  return (
    <nav className="flex flex-col gap-1 p-4">
      <Link to="/" className={linkClass("/")}>
        Home
      </Link>
      <Link to="/sessions/new" className={linkClass("/sessions/new")}>
        New Session
      </Link>
    </nav>
  );
}
