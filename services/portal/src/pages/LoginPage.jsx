import { useEffect, useState } from "react";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useAuth } from "../auth/AuthProvider.jsx";

export function LoginPage() {
  const { config, configError, signIn, signInDevBypass, authenticated, loading } = useAuth();
  const navigate = useNavigate();
  const search = useSearch({ from: "/login" });
  const [error, setError] = useState(/** @type {string | null} */ (null));
  const [signingIn, setSigningIn] = useState(false);

  useEffect(() => {
    if (!loading && authenticated) {
      navigate({ to: search.returnTo || "/" });
    }
  }, [loading, authenticated, navigate, search.returnTo]);

  useEffect(() => {
    if (search.returnTo) {
      sessionStorage.setItem("returnTo", search.returnTo);
    }
  }, [search.returnTo]);

  useEffect(() => {
    if (loading || !config || authenticated) return;
    const providers = config.oidcProviders || [];
    if (providers.length === 1 && !config.devBypass?.enabled) {
      setSigningIn(true);
      signIn(providers[0].id).catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setSigningIn(false);
      });
    }
  }, [loading, config, authenticated, signIn]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100">
        <p className="text-slate-600">Loading…</p>
      </div>
    );
  }

  if (configError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
        <div className="max-w-md rounded-lg border border-red-200 bg-white p-6 text-center">
          <h1 className="text-xl font-semibold text-slate-900">Configuration error</h1>
          <p className="mt-2 text-sm text-red-600">{configError}</p>
        </div>
      </div>
    );
  }

  const providers = config?.oidcProviders ?? [];
  const devEnabled = config?.devBypass?.enabled;

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
      <div className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
        <h1 className="text-2xl font-semibold text-slate-900">Portal</h1>
        <p className="mt-2 text-sm text-slate-600">Sign in to manage your sessions.</p>

        {error && (
          <div className="mt-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="mt-6 flex flex-col gap-3">
          {providers.map((p) => (
            <button
              key={p.id}
              type="button"
              disabled={signingIn}
              onClick={() => {
                setSigningIn(true);
                setError(null);
                signIn(p.id).catch((e) => {
                  setError(e instanceof Error ? e.message : String(e));
                  setSigningIn(false);
                });
              }}
              className="rounded-md bg-portal-accent px-4 py-3 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {p.displayName}
            </button>
          ))}

          {devEnabled && (
            <button
              type="button"
              disabled={signingIn}
              onClick={async () => {
                setSigningIn(true);
                try {
                  await signInDevBypass();
                  navigate({ to: search.returnTo || "/" });
                } catch (e) {
                  setError(e instanceof Error ? e.message : String(e));
                } finally {
                  setSigningIn(false);
                }
              }}
              className="rounded-md border border-slate-300 px-4 py-3 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              Dev sign-in
            </button>
          )}

          {providers.length === 0 && !devEnabled && (
            <p className="text-sm text-red-600">No OIDC providers configured.</p>
          )}
        </div>
      </div>
    </div>
  );
}
