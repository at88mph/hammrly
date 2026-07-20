import { useEffect, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { handleCallback } from "../auth/oidc.js";
import { useAuth } from "../auth/AuthProvider.jsx";

export function AuthCallbackPage() {
  const navigate = useNavigate();
  const { refreshUser } = useAuth();
  const [error, setError] = useState(/** @type {string | null} */ (null));

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const user = await handleCallback();
        await refreshUser();
        if (cancelled) return;
        const returnTo =
          (typeof user?.state === "object" && user?.state?.returnTo) ||
          sessionStorage.getItem("returnTo") ||
          "/";
        sessionStorage.removeItem("returnTo");
        navigate({ to: returnTo });
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [navigate, refreshUser]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
        <div className="max-w-md rounded-lg border border-red-200 bg-white p-6 text-center">
          <h1 className="text-xl font-semibold">Sign-in failed</h1>
          <p className="mt-2 text-sm text-red-600">{error}</p>
          <button
            type="button"
            className="mt-4 text-sm text-portal-accent hover:underline"
            onClick={() => navigate({ to: "/login" })}
          >
            Back to login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100">
      <p className="text-slate-600">Completing sign-in…</p>
    </div>
  );
}
