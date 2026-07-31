import {
  Outlet,
  createRootRoute,
  createRoute,
  createRouter,
  redirect,
} from "@tanstack/react-router";
import { getCurrentUser } from "./auth/oidc.js";
import { getAppBasePath } from "./auth/config.js";
import { useAuth } from "./auth/AuthProvider.jsx";
import { AppShell } from "./components/AppShell.jsx";
import { AuthCallbackPage } from "./pages/AuthCallbackPage.jsx";
import { CampaignDetailPage } from "./pages/CampaignDetailPage.jsx";
import { HomePage } from "./pages/HomePage.jsx";
import { JobDetailPage } from "./pages/JobDetailPage.jsx";
import { LoginPage } from "./pages/LoginPage.jsx";
import { NewSessionPage } from "./pages/NewSessionPage.jsx";
import { SessionDetailPage } from "./pages/SessionDetailPage.jsx";

async function requireAuth({ location }) {
  const user = await getCurrentUser();
  if (!user?.access_token) {
    throw redirect({
      to: "/login",
      search: { returnTo: location.pathname + location.searchStr },
    });
  }
}

function AuthShell({ children }) {
  const { profile, signOut } = useAuth();
  return (
    <AppShell
      profile={profile}
      onSignOut={() =>
        signOut().then(() =>
          window.location.assign(`${getAppBasePath()}/login`),
        )
      }
    >
      {children}
    </AppShell>
  );
}

function AuthenticatedLayout() {
  return (
    <AuthShell>
      <Outlet />
    </AuthShell>
  );
}

const rootRoute = createRootRoute({
  component: () => <Outlet />,
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  validateSearch: (search) => ({
    returnTo: typeof search.returnTo === "string" ? search.returnTo : undefined,
  }),
  component: LoginPage,
});

const authCallbackRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/auth/callback",
  component: AuthCallbackPage,
});

const authenticatedLayoutRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "authenticated",
  beforeLoad: requireAuth,
  component: AuthenticatedLayout,
});

const indexRoute = createRoute({
  getParentRoute: () => authenticatedLayoutRoute,
  path: "/",
  component: HomePage,
});

const newSessionRoute = createRoute({
  getParentRoute: () => authenticatedLayoutRoute,
  path: "/sessions/new",
  component: NewSessionPage,
});

const sessionDetailRoute = createRoute({
  getParentRoute: () => authenticatedLayoutRoute,
  path: "/sessions/$jobId",
  component: SessionDetailPage,
});

const jobDetailRoute = createRoute({
  getParentRoute: () => authenticatedLayoutRoute,
  path: "/jobs/$jobId",
  component: JobDetailPage,
});

const campaignDetailRoute = createRoute({
  getParentRoute: () => authenticatedLayoutRoute,
  path: "/campaigns/$campaignId",
  component: CampaignDetailPage,
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  authCallbackRoute,
  authenticatedLayoutRoute.addChildren([
    indexRoute,
    newSessionRoute,
    sessionDetailRoute,
    jobDetailRoute,
    campaignDetailRoute,
  ]),
]);

const routerBasepath = getAppBasePath();

export const router = createRouter({
  routeTree,
  ...(routerBasepath ? { basepath: routerBasepath } : {}),
  defaultPreload: "intent",
});
