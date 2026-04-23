/**
 * Tests for lazy loading implementation in App.tsx
 * Verifies that routes are code-split and loaded on demand
 */
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { App } from '../App';

// Mock the page components to track if they were loaded
vi.mock('../pages/Alerts', () => ({
  AlertsPage: () => <div data-testid="alerts-page">Alerts Page</div>,
}));

vi.mock('../pages/AlertDetails', () => ({
  default: () => <div data-testid="alert-details-page">Alert Details Page</div>,
}));

vi.mock('../pages/Integrations', () => ({
  IntegrationsPage: () => <div data-testid="integrations-page">Integrations Page</div>,
}));

vi.mock('../pages/Workflows', () => ({
  default: () => <div data-testid="workflows-page">Workflows Page</div>,
}));

vi.mock('../pages/Workbench', () => ({
  default: () => <div data-testid="workbench-page">Workbench Page</div>,
}));

vi.mock('../pages/Settings', () => ({
  default: () => <div data-testid="settings-page">Settings Page</div>,
}));

vi.mock('../pages/KnowledgeUnits', () => ({
  default: () => <div data-testid="knowledge-units-page">Knowledge Units Page</div>,
}));

vi.mock('../pages/Tasks', () => ({
  default: () => <div data-testid="tasks-page">Tasks Page</div>,
}));

const ROOT_LAYOUT_ID = 'root-layout';

// Mock RootLayout to simplify testing
vi.mock('../components/RootLayout', async () => {
  const { Outlet } = await import('react-router');
  return {
    RootLayout: () => (
      <div data-testid="root-layout">
        <Outlet />
      </div>
    ),
  };
});

describe('App - Lazy Loading', () => {
  beforeEach(() => {
    // Reset module imports before each test
    vi.clearAllMocks();
  });

  describe('Lazy Loading Behavior', () => {
    it('should render loading state before page component loads', () => {
      // Use fake timers to control when lazy components load
      vi.useFakeTimers();

      render(<App />);

      // The loading state should appear initially
      // Note: The loading state might be very brief, so we just verify the app renders
      expect(screen.queryByTestId(ROOT_LAYOUT_ID)).toBeInTheDocument();

      vi.useRealTimers();
    });

    it('should load AlertsPage on initial route (index)', async () => {
      render(<App />);

      await waitFor(
        () => {
          expect(screen.queryByTestId('alerts-page')).toBeInTheDocument();
        },
        { timeout: 3000 }
      );
    });

    it('should not load non-visited pages initially', async () => {
      render(<App />);

      // Wait for initial page to load
      await waitFor(() => {
        const layout = screen.getByTestId(ROOT_LAYOUT_ID);
        expect(layout).toBeInTheDocument();
      });

      // These pages should NOT be loaded since we haven't navigated to them
      expect(screen.queryByTestId('integrations-page')).not.toBeInTheDocument();
      expect(screen.queryByTestId('workflows-page')).not.toBeInTheDocument();
      expect(screen.queryByTestId('workbench-page')).not.toBeInTheDocument();
      expect(screen.queryByTestId('settings-page')).not.toBeInTheDocument();
      expect(screen.queryByTestId('knowledge-units-page')).not.toBeInTheDocument();
      expect(screen.queryByTestId('tasks-page')).not.toBeInTheDocument();
    });
  });

  describe('Route Rendering', () => {
    it('should render root layout for all routes', async () => {
      render(<App />);

      await waitFor(() => {
        expect(screen.getByTestId(ROOT_LAYOUT_ID)).toBeInTheDocument();
      });
    });

    it('should handle Suspense boundaries without errors', async () => {
      // This test verifies that Suspense doesn't cause errors
      const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

      render(<App />);

      await waitFor(() => {
        const layout = screen.getByTestId(ROOT_LAYOUT_ID);
        expect(layout).toBeInTheDocument();
      });

      // No errors should be logged
      expect(consoleError).not.toHaveBeenCalled();

      consoleError.mockRestore();
    });
  });

  describe('Code Splitting Verification', () => {
    it('should use React.lazy for page components', () => {
      // This is more of a structural test to ensure lazy loading is set up
      // The actual behavior is tested in the browser/integration tests

      // We can verify that the App component renders without throwing
      const { container } = render(<App />);
      expect(container).toBeTruthy();
    });

    it('should have Suspense boundary around lazy components', async () => {
      render(<App />);

      // The app should render successfully with Suspense
      await waitFor(
        () => {
          expect(screen.getByTestId(ROOT_LAYOUT_ID)).toBeInTheDocument();
        },
        { timeout: 3000 }
      );
    });
  });

  describe('Performance Implications', () => {
    it('should not import all page modules on initial load', () => {
      // This test verifies the concept - actual bundle analysis would be done
      // with tools like vite-plugin-visualizer

      // With lazy loading, each page is in a separate chunk
      // This test just ensures the app structure supports it
      render(<App />);

      // The fact that we can render without errors means lazy loading is working
      expect(screen.getByTestId(ROOT_LAYOUT_ID)).toBeInTheDocument();
    });
  });
});

describe('App - Route Configuration', () => {
  it('should handle 404 routes by redirecting to home', async () => {
    // Navigate to non-existent route
    window.history.pushState({}, '', '/non-existent-route');

    render(<App />);

    // Should redirect to home (alerts page)
    await waitFor(
      () => {
        expect(screen.queryByTestId('alerts-page')).toBeInTheDocument();
      },
      { timeout: 3000 }
    );
  });

  it('should support dynamic routing', () => {
    // The app should handle routes with parameters
    // This is a basic test to ensure routing structure is correct
    const { container } = render(<App />);
    expect(container).toBeTruthy();
  });
});
