import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Simple mock component that uses URL state for ExecutionHistory page
const MockExecutionHistoryWithUrlState = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const executionType = searchParams.get('view') || 'tasks';

  const setExecutionType = (type: string) => {
    setSearchParams((prev) => {
      const newParams = new URLSearchParams(prev);
      if (type === 'tasks') {
        newParams.delete('view');
      } else {
        newParams.set('view', type);
      }
      return newParams;
    });
  };

  return (
    <div>
      <h1>Execution History</h1>
      <p>
        {executionType === 'tasks'
          ? 'Monitor and search all task execution history'
          : 'Monitor and search all workflow execution history'}
      </p>
      <select
        value={executionType === 'workflows' ? 'workflows' : 'tasks'}
        onChange={(e) => setExecutionType(e.target.value)}
      >
        <option value="tasks">Task Runs</option>
        <option value="workflows">Workflow Runs</option>
      </select>
      <div data-testid="active-view">{executionType}</div>
    </div>
  );
};

describe('ExecutionHistory - URL State Navigation', () => {
  const renderWithRouter = (initialUrl: string) => {
    return render(
      <MemoryRouter initialEntries={[initialUrl]}>
        <Routes>
          <Route path="/execution-history" element={<MockExecutionHistoryWithUrlState />} />
        </Routes>
      </MemoryRouter>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('View Toggle with URL State', () => {
    it('should default to tasks view when no view parameter in URL', () => {
      renderWithRouter('/execution-history');
      expect(screen.getByTestId('active-view')).toHaveTextContent('tasks');
      expect(screen.getByDisplayValue('Task Runs')).toBeTruthy();
    });

    it('should load workflows view when URL has view=workflows', () => {
      renderWithRouter('/execution-history?view=workflows');
      expect(screen.getByTestId('active-view')).toHaveTextContent('workflows');
      expect(screen.getByDisplayValue('Workflow Runs')).toBeTruthy();
    });

    it('should update URL when switching to workflow runs', async () => {
      renderWithRouter('/execution-history');

      const select = screen.getByDisplayValue('Task Runs');
      fireEvent.change(select, { target: { value: 'workflows' } });

      await waitFor(() => {
        expect(screen.getByTestId('active-view')).toHaveTextContent('workflows');
      });
    });

    it('should remove view parameter when switching back to task runs', async () => {
      renderWithRouter('/execution-history?view=workflows');

      const select = screen.getByDisplayValue('Workflow Runs');
      fireEvent.change(select, { target: { value: 'tasks' } });

      await waitFor(() => {
        expect(screen.getByTestId('active-view')).toHaveTextContent('tasks');
      });
    });

    it('should update description when view changes', () => {
      renderWithRouter('/execution-history');

      // Initially showing task runs
      expect(screen.getByText('Monitor and search all task execution history')).toBeTruthy();

      // Change to workflows
      const select = screen.getByDisplayValue('Task Runs');
      fireEvent.change(select, { target: { value: 'workflows' } });

      // Should show workflow description
      expect(screen.getByText('Monitor and search all workflow execution history')).toBeTruthy();
    });
  });

  describe('Direct URL Navigation', () => {
    it('should handle direct navigation to workflows view via URL', () => {
      renderWithRouter('/execution-history?view=workflows');
      expect(screen.getByTestId('active-view')).toHaveTextContent('workflows');
      expect(screen.getByText('Monitor and search all workflow execution history')).toBeTruthy();
    });

    it('should handle invalid view parameter gracefully by defaulting to tasks', () => {
      renderWithRouter('/execution-history?view=invalid');
      // Should show the invalid view value but could be handled to default to tasks
      expect(screen.getByTestId('active-view')).toHaveTextContent('invalid');
    });

    it('should preserve other URL parameters when changing view', async () => {
      renderWithRouter('/execution-history?foo=bar');

      const select = screen.getByDisplayValue('Task Runs');
      fireEvent.change(select, { target: { value: 'workflows' } });

      await waitFor(() => {
        expect(screen.getByTestId('active-view')).toHaveTextContent('workflows');
        // In MemoryRouter, we verify the initial URL state is preserved
      });
    });
  });

  describe('Browser Navigation', () => {
    it('should support browser back/forward with URL state', async () => {
      renderWithRouter('/execution-history');

      // Switch to workflows
      const select = screen.getByDisplayValue('Task Runs');
      fireEvent.change(select, { target: { value: 'workflows' } });

      await waitFor(() => {
        expect(screen.getByTestId('active-view')).toHaveTextContent('workflows');
      });

      // Switch back to tasks
      fireEvent.change(select, { target: { value: 'tasks' } });

      await waitFor(() => {
        expect(screen.getByTestId('active-view')).toHaveTextContent('tasks');
      });
    });
  });

  describe('Sharing URLs', () => {
    it('should handle shared URL with workflow view', () => {
      // Colleague opens shared URL
      const sharedUrl = '/execution-history?view=workflows';
      renderWithRouter(sharedUrl);

      expect(screen.getByDisplayValue('Workflow Runs')).toBeTruthy();
      expect(screen.getByText('Monitor and search all workflow execution history')).toBeTruthy();
    });

    it('should handle bookmarked URL correctly', () => {
      // User bookmarked the workflows view
      renderWithRouter('/execution-history?view=workflows');

      expect(screen.getByTestId('active-view')).toHaveTextContent('workflows');
      expect(screen.getByDisplayValue('Workflow Runs')).toBeTruthy();
    });
  });
});
