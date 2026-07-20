import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { initOidcManagers, getCurrentUser, signIn as oidcSignIn, signInDev, signOut as oidcSignOut, parseJwtClaims, getAccessToken } from "./oidc.js";
import { loadConfig } from "./config.js";

/** @typedef {{ sub?: string, tenantId?: string, displayName?: string }} AuthProfile */

/** @type {React.Context<{ loading: boolean, authenticated: boolean, profile: AuthProfile | null, signIn: (id: string) => Promise<void>, signInDevBypass: () => Promise<void>, signOut: () => Promise<void>, getToken: () => Promise<string | null>, config: import('./config.js').PortalConfig | null, configError: string | null }>} */
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [loading, setLoading] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [profile, setProfile] = useState(/** @type {AuthProfile | null} */ (null));
  const [config, setConfig] = useState(/** @type {import('./config.js').PortalConfig | null} */ (null));
  const [configError, setConfigError] = useState(/** @type {string | null} */ (null));

  const refreshUser = useCallback(async () => {
    const user = await getCurrentUser();
    if (!user?.access_token) {
      setAuthenticated(false);
      setProfile(null);
      return;
    }
    const claims = parseJwtClaims(user.access_token);
    setAuthenticated(true);
    setProfile({
      sub: claims.sub || user.profile?.sub,
      tenantId: claims.hammrly_tenant_id,
      displayName: claims.name || claims.preferred_username || claims.sub,
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cfg = await loadConfig();
        if (cancelled) return;
        setConfig(cfg);
        initOidcManagers(cfg);
        if (cfg.devBypass?.enabled && (cfg.oidcProviders?.length ?? 0) === 0) {
          await signInDev();
        }
        await refreshUser();
      } catch (e) {
        if (!cancelled) {
          setConfigError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshUser]);

  const signIn = useCallback(async (providerId) => {
    await oidcSignIn(providerId);
  }, []);

  const signInDevBypass = useCallback(async () => {
    await signInDev();
    await refreshUser();
  }, [refreshUser]);

  const signOut = useCallback(async () => {
    await oidcSignOut();
    setAuthenticated(false);
    setProfile(null);
  }, []);

  const getToken = useCallback(() => getAccessToken(), []);

  const value = useMemo(
    () => ({
      loading,
      authenticated,
      profile,
      signIn,
      signInDevBypass,
      signOut,
      getToken,
      config,
      configError,
      refreshUser,
    }),
    [loading, authenticated, profile, signIn, signInDevBypass, signOut, getToken, config, configError, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
