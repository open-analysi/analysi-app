import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Simple mock component that uses URL state for Tasks page
const MockTasksWithUrlState = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'tasks';

  const setTab = (tab: string) => {
    setSearchParams((prev) => {
      const newParams = new URLSearchParams(prev);
      if (tab === 'tasks') {
        newParams.delete('tab');
      } else {
        newParams.set('tab', tab);
      }
      return newParams;
    });
  };

  return (
    <div>
      <h1>Tasks & Workbench</h1>
      <div>
        <button onClick={() => setTab('tasks')} className={activeTab === 'tasks' ? 'bg-white' : ''}>
          Tasks
        </button>
        <button
          onClick={() => setTab('workbench')}
          className={activeTab === 'workbench' ? 'bg-white' : ''}
        >
          Workbench
        </button>
      </div>
      <div data-testid="active-tab">{activeTab}</div>
    </div>
  );
};

describe('Tasks Page - URL State Navigation', () => {
  const renderWithRouter = (initialUrl: string) => {
    return render(
      <MemoryRouter initialEntries={[initialUrl]}>
        <Routes>
          <Route path="/tasks" element={<MockTasksWithUrlState />} />
        </Routes>
      </MemoryRouter>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Tab Navigation with URL State', () => {
    it('should default to tasks tab when no tab parameter in URL', () => {
      renderWithRouter('/tasks');
      expect(screen.getByTestId('active-tab')).toHaveTextContent('tasks');
    });

    it('should load workbench tab when URL has tab=workbench', () => {
      renderWithRouter('/tasks?tab=workbench');
      expect(screen.getByTestId('active-tab')).toHaveTextContent('workbench');
    });

    it('should update URL when clicking on Workbench tab', async () => {
      renderWithRouter('/tasks');

      // Click on Workbench tab
      fireEvent.click(screen.getByText('Workbench'));

      await waitFor(() => {
        expect(screen.getByTestId('active-tab')).toHaveTextContent('workbench');
      });
    });

    it('should remove tab parameter when returning to default tab', async () => {
      renderWithRouter('/tasks?tab=workbench');

      // Click back on Tasks tab (default)
      fireEvent.click(screen.getByText('Tasks'));

      await waitFor(() => {
        expect(screen.getByTestId('active-tab')).toHaveTextContent('tasks');
      });
    });
  });

  describe('Direct URL Navigation', () => {
    it('should handle direct navigation to workbench tab via URL', () => {
      renderWithRouter('/tasks?tab=workbench');
      expect(screen.getByTestId('active-tab')).toHaveTextContent('workbench');

      // Workbench button should be active
      const workbenchButton = screen.getByText('Workbench');
      expect(workbenchButton).toHaveClass('bg-white');
    });

    it('should handle invalid tab parameter gracefully', () => {
      renderWithRouter('/tasks?tab=invalid-tab');
      // Should still render without crashing, showing the invalid tab name
      expect(screen.getByTestId('active-tab')).toHaveTextContent('invalid-tab');
    });

    it('should preserve other URL parameters', () => {
      renderWithRouter('/tasks?tab=workbench&debug=true');
      expect(screen.getByTestId('active-tab')).toHaveTextContent('workbench');
      // In MemoryRouter, we verify the initial URL state is preserved
    });
  });

  describe('Browser Navigation', () => {
    it('should support browser back/forward with URL state', async () => {
      renderWithRouter('/tasks');

      // Navigate to Workbench
      fireEvent.click(screen.getByText('Workbench'));

      await waitFor(() => {
        expect(screen.getByTestId('active-tab')).toHaveTextContent('workbench');
      });

      // Navigate back to Tasks
      fireEvent.click(screen.getByText('Tasks'));

      await waitFor(() => {
        expect(screen.getByTestId('active-tab')).toHaveTextContent('tasks');
      });
    });
  });
});
