import React from 'react';

import { createMemoryRouter, RouterProvider } from 'react-router';

/**
 * Creates a test router with React Router v7 future flags enabled
 * This helper prevents future flag warnings in tests
 */
export function createTestRouter(routes: any[], initialEntries?: string[]) {
  return createMemoryRouter(routes, {
    initialEntries,
    future: {
      v7_startTransition: true,
      v7_relativeSplatPath: true,
    } as any, // Type assertion for v7 future flags not yet in types
  });
}

/**
 * Wrapper component for tests that need routing with future flags
 * Usage: renderWithRouter(<YourComponent />, { route: '/path' })
 */
export function TestRouterProvider({
  children,
  initialEntries = ['/'],
}: {
  children: React.ReactElement;
  initialEntries?: string[];
}) {
  const router = createMemoryRouter(
    [
      {
        path: '*',
        element: children,
      },
    ],
    {
      initialEntries,
      future: {
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      } as any, // Type assertion for v7 future flags not yet in types
    }
  );

  return <RouterProvider router={router} />;
}
