import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getUnreadNotificationCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  streamNotifications,
} from "../api/query.js";

/**
 * Inbox list + unread count + SSE live updates + toast messages.
 */
export function useNotifications() {
  const queryClient = useQueryClient();
  const [toast, setToast] = useState(/** @type {string | null} */ (null));
  const toastTimer = useRef(/** @type {ReturnType<typeof setTimeout> | null} */ (null));

  const unreadQuery = useQuery({
    queryKey: ["notifications", "unread_count"],
    queryFn: getUnreadNotificationCount,
    refetchInterval: 60000,
  });

  const listQuery = useQuery({
    queryKey: ["notifications", "list"],
    queryFn: () => listNotifications({ limit: 30 }),
  });

  const showToast = useCallback((message) => {
    setToast(message);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 6000);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    async function run() {
      while (!cancelled) {
        try {
          await streamNotifications((ev) => {
            if (ev.type === "snapshot" || ev.type === "notification") {
              const unread = Number(ev.data.unread_count ?? 0);
              queryClient.setQueryData(["notifications", "unread_count"], {
                unread_count: unread,
              });
              if (ev.type === "notification") {
                queryClient.invalidateQueries({ queryKey: ["notifications", "list"] });
                showToast(
                  unread === 1
                    ? "1 new notification"
                    : `${unread} unread notification${unread === 1 ? "" : "s"}`,
                );
              }
            }
          }, controller.signal);
        } catch (err) {
          if (cancelled || controller.signal.aborted) return;
          // Backoff then reconnect
          await new Promise((r) => setTimeout(r, 5000));
        }
      }
    }

    run();
    return () => {
      cancelled = true;
      controller.abort();
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
  }, [queryClient, showToast]);

  const markRead = useCallback(
    async (id) => {
      await markNotificationRead(id);
      await queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    [queryClient],
  );

  const markAllRead = useCallback(async () => {
    await markAllNotificationsRead();
    await queryClient.invalidateQueries({ queryKey: ["notifications"] });
  }, [queryClient]);

  return {
    unreadCount: unreadQuery.data?.unread_count ?? 0,
    items: listQuery.data?.items ?? [],
    isLoading: listQuery.isLoading,
    toast,
    dismissToast: () => setToast(null),
    markRead,
    markAllRead,
    refetchList: () => listQuery.refetch(),
  };
}
