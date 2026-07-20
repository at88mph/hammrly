import { AppHeader } from "./AppHeader.jsx";
import { SidebarNav } from "./SidebarNav.jsx";

export function AppShell({ profile, onSignOut, children }) {
  return (
    <div className="grid min-h-screen grid-rows-[auto_1fr]">
      <AppHeader profile={profile} onSignOut={onSignOut} />
      <div className="grid grid-cols-1 md:grid-cols-[240px_1fr]">
        <aside className="border-r border-slate-200 bg-portal-sidebar">
          <SidebarNav />
        </aside>
        <main className="p-6">{children}</main>
      </div>
    </div>
  );
}
