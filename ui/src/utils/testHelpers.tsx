import React from 'react';

import { createMemoryRouter, RouterProvider, type RouteObject } from 'react-router';

/**
 * Creates a memory router for tests.
 *
 * Historically this helper enabled the v7_startTransition / v7_relativeSplatPath
 * future flags, but those are now the defaults in react-router 7 and no longer
 * exist on FutureConfig — the helper just thin-wraps createMemoryRouter for
 * call-site convenience.
 */
export function createTestRouter(
  routes: RouteObject[],
  initialEntries?: string[]
): ReturnType<typeof createMemoryRouter> {
  return createMemoryRouter(routes, { initialEntries });
}

/**
 * Wrapper component for tests that need routing.
 * Usage: renderWithRouter(<YourComponent />, { route: '/path' })
 */
export function TestRouterProvider({
  children,
  initialEntries = ['/'],
}: Readonly<{
  children: React.ReactElement;
  initialEntries?: string[];
}>) {
  const router = createMemoryRouter(
    [
      {
        path: '*',
        element: children,
      },
    ],
    { initialEntries }
  );

  return <RouterProvider router={router} />;
}
