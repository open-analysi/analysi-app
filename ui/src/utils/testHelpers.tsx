import React from 'react';

import { createMemoryRouter, RouterProvider, type RouteObject } from 'react-router';

export function createTestRouter(
  routes: RouteObject[],
  initialEntries?: string[]
): ReturnType<typeof createMemoryRouter> {
  return createMemoryRouter(routes, { initialEntries });
}

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
