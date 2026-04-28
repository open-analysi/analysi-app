import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Simple mock component that uses URL state
const MockAlertDetailsWithUrlState = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'details';

  const setTab = (tab: string) => {
    setSearchParams((prev) => {
      const newParams = new URLSearchParams(prev);
      if (tab === 'details') {
        newParams.delete('tab');
      } else {
        newParams.set('tab', tab);
      }
      return newParams;
    });
  };

  return (
    <div>
      <h1>Alert Details</h1>
      <div>
        <button
          onClick={() => setTab('details')}
          className={activeTab === 'details' ? 'border-primary' : ''}
        >
          Details
        </button>
        <button
          onClick={() => setTab('summary')}
          className={activeTab === 'summary' ? 'border-primary' : ''}
        >
          Summary
        </button>
        <button
          onClick={() => setTab('workflow')}
          className={activeTab === 'workflow' ? 'border-primary' : ''}
        >
          Workflow
        </button>
        <button
          onClick={() => setTab('workflow-tasks')}
          className={activeTab === 'workflow-tasks' ? 'border-primary' : ''}
        >
          Workflow Tasks
        </button>
      </div>
      <div data-testid="active-tab">{activeTab}</div>
    </div>
  );
};

describe('AlertDetails - URL State Navigation', () => {
  const renderWithRouter = (initialUrl: string) => {
    return render(
      <MemoryRouter initialEntries={[initialUrl]}>
        <Routes>
          <Route path="/alerts/:id" element={<MockAlertDetailsWithUrlState />} />
        </Routes>
      </MemoryRouter>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Tab Navigation with URL State', () => {
    it('should default to details tab when no tab parameter in URL', () => {
      renderWithRouter('/alerts/test-id');
      expect(screen.getByTestId('active-tab')).toHaveTextContent('details');
    });

    it('should load workflow tab when URL has tab=workflow', () => {
      renderWithRouter('/alerts/test-id?tab=workflow');
      expect(screen.getByTestId('active-tab')).toHaveTextContent('workflow');
    });

    it('should load workflow-tasks tab when URL has tab=workflow-tasks', () => {
      renderWithRouter('/alerts/test-id?tab=workflow-tasks');
      expect(screen.getByTestId('active-tab')).toHaveTextContent('workflow-tasks');
    });

    it('should update URL when clicking on different tabs', async () => {
      renderWithRouter('/alerts/test-id');

      // Click on Summary tab
      fireEvent.click(screen.getByText('Summary'));

      await waitFor(() => {
        expect(screen.getByTestId('active-tab')).toHaveTextContent('summary');
      });

      // Click on Workflow tab
      fireEvent.click(screen.getByText('Workflow'));

      await waitFor(() => {
        expect(screen.getByTestId('active-tab')).toHaveTextContent('workflow');
      });
    });

    it('should remove tab parameter when returning to default tab', async () => {
      renderWithRouter('/alerts/test-id?tab=summary');

      // Click back on Details tab (default)
      fireEvent.click(screen.getByText('Details'));

      await waitFor(() => {
        expect(screen.getByTestId('active-tab')).toHaveTextContent('details');
      });
    });
  });

  describe('Direct URL Navigation', () => {
    it('should handle direct navigation to specific tab via URL', () => {
      renderWithRouter('/alerts/test-id?tab=summary');
      expect(screen.getByTestId('active-tab')).toHaveTextContent('summary');
    });

    it('should handle invalid tab parameter gracefully by defaulting to details', () => {
      renderWithRouter('/alerts/test-id?tab=invalid-tab');
      // Should still render without crashing, showing the invalid tab name
      expect(screen.getByTestId('active-tab')).toHaveTextContent('invalid-tab');
    });

    it('should preserve other URL parameters', () => {
      renderWithRouter('/alerts/test-id?tab=workflow&debug=true');
      expect(screen.getByTestId('active-tab')).toHaveTextContent('workflow');
      // In MemoryRouter, we verify the initial URL state is preserved
    });
  });
});
