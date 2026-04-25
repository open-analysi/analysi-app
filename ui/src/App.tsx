import React, { lazy, StrictMode, Suspense, useEffect } from 'react';

import { OidcProvider, OidcSecure, useOidc } from '@axa-fr/react-oidc';
import { LockClosedIcon } from '@heroicons/react/24/outline';
import {
  createBrowserRouter,
  RouterProvider,
  Navigate,
  useRouteError,
  isRouteErrorResponse,
} from 'react-router';

import AuthInitializer from './components/auth/AuthInitializer';
import { RootLayout } from './components/RootLayout';

// Lazy load all page components for better code splitting
const AccountSettings = lazy(() =>
  import('./pages/AccountSettings').then((m) => ({ default: m.AccountSettings }))
);
const AlertDetailsPage = lazy(() =>
  import('./pages/AlertDetails').then((m) => ({ default: m.AlertDetailsPage }))
);
const AlertsPage = lazy(() => import('./pages/Alerts').then((m) => ({ default: m.AlertsPage })));
const AuditTrailPage = lazy(() =>
  import('./pages/AuditTrail').then((m) => ({ default: m.AuditTrailPage }))
);
const ExecutionHistory = lazy(() => import('./pages/ExecutionHistory'));
const IntegrationsPage = lazy(() =>
  import('./pages/Integrations').then((m) => ({ default: m.IntegrationsPage }))
);
const KnowledgeGraphPage = lazy(() => import('./pages/KnowledgeGraph'));
const KnowledgeUnitsPage = lazy(() => import('./pages/KnowledgeUnits'));
const Settings = lazy(() => import('./pages/Settings'));
const TasksPage = lazy(() => import('./pages/Tasks'));
const TenantDebug = lazy(() => import('./pages/TenantDebug'));
const WorkbenchPage = lazy(() => import('./pages/Workbench'));
const SkillsPage = lazy(() => import('./pages/Skills'));
const WorkflowRunPage = lazy(() => import('./pages/WorkflowRunPage'));
const WorkflowsPage = lazy(() => import('./pages/Workflows'));

// Loading fallback component
const PageLoadingFallback: React.FC = () => (
  <div className="flex items-center justify-center h-screen bg-dark-900">
    <div className="flex flex-col items-center space-y-4">
      <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin" />
      <p className="text-gray-400 text-sm">Loading...</p>
    </div>
  </div>
);

// Route-level error boundary for nice error display
const RouteErrorBoundary: React.FC = () => {
  const error = useRouteError();
  const is404 = isRouteErrorResponse(error) && error.status === 404;

  const title = is404 ? 'Page Not Found' : 'Something went wrong';
  let message = 'An unexpected error occurred while loading this page.';
  if (is404) {
    message = "The page you're looking for doesn't exist or has been moved.";
  } else if (error instanceof Error) {
    message = error.message;
  }

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="max-w-md w-full mx-4 text-center">
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-8 shadow-lg">
          <div className="w-14 h-14 mx-auto mb-4 rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center">
            <svg
              className="w-7 h-7 text-red-400"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
              />
            </svg>
          </div>
          <h2 className="text-xl font-semibold text-gray-100 mb-2">{title}</h2>
          <p className="text-sm text-gray-400 mb-6">{message}</p>
          {import.meta?.env?.DEV && error instanceof Error && error.stack && (
            <details className="mb-6 text-left">
              <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-400">
                Stack trace
              </summary>
              <pre className="mt-2 text-xs text-gray-500 overflow-auto max-h-40 p-3 bg-dark-900 rounded-lg border border-dark-600">
                {error.stack}
              </pre>
            </details>
          )}
          <div className="flex gap-3 justify-center">
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 text-sm font-medium text-gray-300 bg-dark-700 hover:bg-dark-600 border border-dark-500 rounded-lg transition-colors"
            >
              Reload Page
            </button>
            <a
              href="/"
              className="px-4 py-2 text-sm font-medium text-white bg-primary hover:bg-primary/90 rounded-lg transition-colors"
            >
              Go Home
            </a>
          </div>
        </div>
      </div>
    </div>
  );
};

// Placeholder for integration details page
const IntegrationDetailsPlaceholder: React.FC = () => {
  return <Navigate to="/integrations" replace />;
};

// Wrapper component to add Suspense boundary to each route
const LazyRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <Suspense fallback={<PageLoadingFallback />}>{children}</Suspense>
);

const router = createBrowserRouter([
  {
    path: '/',
    element: <RootLayout />,
    errorElement: (
      <RootLayout>
        <RouteErrorBoundary />
      </RootLayout>
    ),
    children: [
      {
        index: true,
        element: (
          <LazyRoute>
            <AlertsPage />
          </LazyRoute>
        ),
      },
      {
        path: 'alerts',
        element: (
          <LazyRoute>
            <AlertsPage />
          </LazyRoute>
        ),
      },
      {
        path: 'alerts/:id',
        element: (
          <LazyRoute>
            <AlertDetailsPage />
          </LazyRoute>
        ),
      },
      {
        path: 'integrations',
        element: (
          <LazyRoute>
            <IntegrationsPage />
          </LazyRoute>
        ),
      },
      {
        path: 'integrations/:integrationId',
        element: <IntegrationDetailsPlaceholder />,
      },
      {
        path: 'knowledge-units',
        element: (
          <LazyRoute>
            <KnowledgeUnitsPage />
          </LazyRoute>
        ),
      },
      {
        path: 'tasks',
        element: (
          <LazyRoute>
            <TasksPage />
          </LazyRoute>
        ),
      },
      {
        path: 'workbench',
        element: (
          <LazyRoute>
            <WorkbenchPage />
          </LazyRoute>
        ),
      },
      {
        path: 'workflows',
        element: (
          <LazyRoute>
            <WorkflowsPage />
          </LazyRoute>
        ),
      },
      {
        path: 'workflows/:workflowId',
        element: (
          <LazyRoute>
            <WorkflowsPage />
          </LazyRoute>
        ),
      },
      {
        path: 'workflows/:workflowId/edit',
        element: (
          <LazyRoute>
            <WorkflowsPage />
          </LazyRoute>
        ),
      },
      {
        path: 'skills',
        element: (
          <LazyRoute>
            <SkillsPage />
          </LazyRoute>
        ),
      },
      {
        path: 'knowledge-graph',
        element: (
          <LazyRoute>
            <KnowledgeGraphPage />
          </LazyRoute>
        ),
      },
      {
        path: 'settings',
        element: (
          <LazyRoute>
            <Settings />
          </LazyRoute>
        ),
      },
      {
        path: 'tenant-debug',
        element: (
          <LazyRoute>
            <TenantDebug />
          </LazyRoute>
        ),
      },
      {
        path: 'audit',
        element: (
          <LazyRoute>
            <AuditTrailPage />
          </LazyRoute>
        ),
      },
      {
        path: 'account-settings',
        element: (
          <LazyRoute>
            <AccountSettings />
          </LazyRoute>
        ),
      },
      {
        path: 'execution-history',
        element: (
          <LazyRoute>
            <ExecutionHistory />
          </LazyRoute>
        ),
      },
      {
        path: 'workflow-runs/:runId',
        element: (
          <LazyRoute>
            <WorkflowRunPage />
          </LazyRoute>
        ),
      },
      // OIDC callback routes — show a loading spinner while the OidcProvider
      // processes the authorization code. Without these, the catch-all route
      // redirects to "/" (Integrations) before the OIDC library can handle the callback.
      {
        path: 'authentication/callback',
        element: <PageLoadingFallback />,
      },
      {
        path: 'authentication/silent-callback',
        element: <PageLoadingFallback />,
      },
      // Catch-all route for 404s
      {
        path: '*',
        element: <Navigate to="/" replace />,
      },
    ],
  },
]);

// OIDC configuration for Keycloak
// Authority and client are configurable via env vars so the same build
// works in dev (localhost Keycloak) and production (real IdP).
const oidcConfiguration = {
  client_id: (import.meta.env.VITE_OIDC_CLIENT_ID as string | undefined) ?? 'analysi-app',
  redirect_uri: `${window.location.origin}/authentication/callback`,
  silent_redirect_uri: `${window.location.origin}/authentication/silent-callback`,
  scope: 'openid profile email',
  authority:
    (import.meta.env.VITE_OIDC_AUTHORITY as string | undefined) ??
    'http://localhost:8080/realms/analysi',
  service_worker_relative_url: '/OidcServiceWorker.js',
  // Allow session storage fallback when ServiceWorker is unavailable
  service_worker_only: false,
};

// When the OIDC session expires, automatically re-trigger login instead of
// showing the library's default "Session timed out" dead-end page.
const SessionLostAutoRedirect: React.FC = () => {
  const { login } = useOidc();
  useEffect(() => {
    void login(window.location.pathname + window.location.search);
  }, [login]);
  return <PageLoadingFallback />;
};

// Shown when the OIDC callback fails (e.g., expired or invalid authorization
// code after a logout). This component renders *outside* OidcSecure, so hooks
// like useOidc() are not available.
//
// On mount we clear all OIDC state (service worker registration, sessionStorage,
// localStorage) so the next navigation to "/" starts a completely fresh login
// flow instead of looping back here with a stale service worker.
const AuthenticationErrorFallback: React.FC = () => {
  const [clearing, setClearing] = React.useState(true);

  useEffect(() => {
    const cleanup = async () => {
      try {
        // 1. Unregister the OIDC service worker so stale state can't interfere
        if ('serviceWorker' in navigator) {
          const registrations = await navigator.serviceWorker.getRegistrations();
          const oidcWorkers = registrations.filter((r) => {
            const url = (r.active ?? r.installing ?? r.waiting)?.scriptURL ?? '';
            return url.includes('OidcServiceWorker');
          });
          await Promise.all(oidcWorkers.map((r) => r.unregister()));
        }
      } catch {
        /* service worker API may be unavailable or throw — continue cleanup */
      }

      // 2. Clear sessionStorage & localStorage entries used by @axa-fr/react-oidc
      //    (The library stores PKCE state, nonces, and tokens here.)
      try {
        sessionStorage.clear();
      } catch {
        /* ignore */
      }
      try {
        // Only remove OIDC-related keys, not everything
        const keysToRemove: string[] = [];
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i);
          if (key && (key.startsWith('oidc.') || key.includes('oidc'))) {
            keysToRemove.push(key);
          }
        }
        keysToRemove.forEach((k) => localStorage.removeItem(k));
      } catch {
        /* ignore */
      }

      setClearing(false);
    };

    void cleanup();
  }, []);

  const handleSignIn = (e: React.MouseEvent) => {
    e.preventDefault();
    // Full page reload to "/" ensures the OidcProvider re-initializes from scratch
    // (a client-side navigation would reuse the same broken provider instance).
    window.location.replace('/');
  };

  if (clearing) {
    return <PageLoadingFallback />;
  }

  return (
    <div className="flex items-center justify-center h-screen bg-dark-900">
      <div className="max-w-md w-full mx-4 text-center">
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-8 shadow-lg">
          <div className="w-14 h-14 mx-auto mb-4 rounded-full bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
            <LockClosedIcon className="w-7 h-7 text-amber-400" />
          </div>
          <h2 className="text-xl font-semibold text-gray-100 mb-2">Session Expired</h2>
          <p className="text-sm text-gray-400 mb-6">
            Your session has expired or the login link is no longer valid. Please sign in again to
            continue.
          </p>
          <a
            href="/"
            onClick={handleSignIn}
            className="inline-block px-6 py-2.5 text-sm font-medium text-white bg-primary hover:bg-primary/90 rounded-lg transition-colors"
          >
            Sign In
          </a>
        </div>
      </div>
    </div>
  );
};

// Allow disabling OIDC for E2E tests or development without Keycloak.
// Set VITE_DISABLE_AUTH=true in the environment to bypass authentication.
const disableAuth = import.meta.env.VITE_DISABLE_AUTH === 'true';

export const App: React.FC = () => {
  if (disableAuth) {
    return (
      <StrictMode>
        <RouterProvider router={router} />
      </StrictMode>
    );
  }

  return (
    <OidcProvider
      configuration={oidcConfiguration}
      sessionLostComponent={SessionLostAutoRedirect}
      authenticatingErrorComponent={AuthenticationErrorFallback}
    >
      <StrictMode>
        <OidcSecure>
          <AuthInitializer>
            <RouterProvider router={router} />
          </AuthInitializer>
        </OidcSecure>
      </StrictMode>
    </OidcProvider>
  );
};

export default App;
