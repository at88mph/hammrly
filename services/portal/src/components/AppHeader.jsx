import { NotificationBell } from "./NotificationBell.jsx";

const logoUrl = `${import.meta.env.BASE_URL}hammrly-logo.png`;

export function AppHeader({ profile, onSignOut }) {
  return (
    <header className="flex h-14 items-center justify-between border-b border-slate-700 bg-portal-header px-6 text-white">
      <div className="flex items-center gap-3">
        <img
          src={logoUrl}
          alt="Hammrly"
          className="h-9 w-9 rounded-full"
        />
        <span className="text-lg font-semibold tracking-tight">Hammrly - Portal</span>
        {import.meta.env.DEV && (
          <span className="rounded bg-amber-500/20 px-2 py-0.5 text-xs text-amber-200">dev</span>
        )}
      </div>
      <div className="flex items-center gap-4 text-sm">
        {profile && <NotificationBell />}
        {profile && (
          <span className="text-slate-300">
            {profile.displayName || profile.sub}
            {profile.tenantId && (
              <span className="ml-2 text-slate-400">({profile.tenantId})</span>
            )}
          </span>
        )}
        <button
          type="button"
          onClick={onSignOut}
          className="rounded border border-slate-500 px-3 py-1 text-slate-200 hover:bg-slate-700"
        >
          Sign out
        </button>
      </div>
    </header>
  );
}
