import { useEffect, useRef, useState } from "react";
import { Link } from "@tanstack/react-router";
import { useNotifications } from "../hooks/useNotifications.js";
import { formatRelativeTime } from "../utils.js";

export function NotificationBell() {
  const {
    unreadCount,
    items,
    toast,
    dismissToast,
    markRead,
    markAllRead,
    refetchList,
  } = useNotifications();
  const [open, setOpen] = useState(false);
  const panelRef = useRef(/** @type {HTMLDivElement | null} */ (null));

  useEffect(() => {
    function onDocClick(e) {
      if (!panelRef.current?.contains(e.target)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  return (
    <div className="relative" ref={panelRef}>
      {toast && (
        <div className="absolute right-0 top-10 z-50 w-72 rounded-md border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-white shadow-lg">
          <div className="flex items-start justify-between gap-2">
            <span>{toast}</span>
            <button
              type="button"
              className="text-slate-400 hover:text-white"
              onClick={dismissToast}
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        </div>
      )}

      <button
        type="button"
        className="relative rounded border border-slate-500 px-2 py-1 text-slate-200 hover:bg-slate-700"
        aria-label="Notifications"
        onClick={() => {
          setOpen((v) => !v);
          if (!open) refetchList();
        }}
      >
        <svg
          aria-hidden
          className="h-4 w-4"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M15 17h5l-1.4-1.4A2 2 0 0 1 18 14.2V11a6 6 0 1 0-12 0v3.2c0 .5-.2 1-.6 1.4L4 17h5" />
          <path d="M9 17a3 3 0 0 0 6 0" />
        </svg>
        {unreadCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-40 mt-2 w-96 max-w-[calc(100vw-2rem)] rounded-lg border border-slate-200 bg-white text-slate-900 shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
            <span className="text-sm font-semibold">Notifications</span>
            {unreadCount > 0 && (
              <button
                type="button"
                className="text-xs text-portal-accent hover:underline"
                onClick={() => markAllRead()}
              >
                Mark all read
              </button>
            )}
          </div>
          <ul className="max-h-80 overflow-y-auto">
            {items.length === 0 && (
              <li className="px-3 py-6 text-center text-sm text-slate-500">
                No notifications yet.
              </li>
            )}
            {items.map((n) => {
              const campaignId =
                n.resource_type === "campaign"
                  ? n.resource_id
                  : /** @type {string|undefined} */ (n.body_json?.campaign_id);
              const unread = !n.read_at;
              return (
                <li
                  key={n.id}
                  className={`border-b border-slate-100 last:border-0 ${
                    unread ? "bg-blue-50/60" : ""
                  }`}
                >
                  {campaignId ? (
                    <Link
                      to="/campaigns/$campaignId"
                      params={{ campaignId }}
                      className="block px-3 py-3 hover:bg-slate-50"
                      onClick={() => {
                        if (unread) markRead(n.id);
                        setOpen(false);
                      }}
                    >
                      <NotificationRow n={n} />
                    </Link>
                  ) : (
                    <button
                      type="button"
                      className="block w-full px-3 py-3 text-left hover:bg-slate-50"
                      onClick={() => {
                        if (unread) markRead(n.id);
                      }}
                    >
                      <NotificationRow n={n} />
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

function NotificationRow({ n }) {
  const failCount = n.body_json?.fail_count;
  return (
    <>
      <div className="text-sm font-medium text-slate-900">{n.subject}</div>
      <div className="mt-0.5 text-xs text-slate-500">
        {formatRelativeTime(n.created_at)}
        {typeof failCount === "number" && failCount > 0
          ? ` · ${failCount} failed`
          : ""}
      </div>
    </>
  );
}
