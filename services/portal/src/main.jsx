import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { AuthProvider, useAuth } from "./auth/AuthProvider.jsx";
import { setTokenGetter } from "./api/client.js";
import { router } from "./router.jsx";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: true,
    },
  },
});

function TokenBridge({ children }) {
  const { getToken } = useAuth();
  useEffect(() => {
    setTokenGetter(getToken);
  }, [getToken]);
  return children;
}

function AppRoot() {
  const { loading } = useAuth();
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100 text-slate-600">
        Loading…
      </div>
    );
  }
  return (
    <TokenBridge>
      <RouterProvider router={router} />
    </TokenBridge>
  );
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AppRoot />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
