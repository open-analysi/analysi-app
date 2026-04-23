import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

import { AlertAnalysis } from '../../../types/alert';
import { AnalysisRunSelector } from '../AnalysisRunSelector';

// Mock timezone store
vi.mock('../../../store/timezoneStore', () => ({
  useTimezoneStore: () => ({
    timezone: 'UTC',
  }),
}));

const mockAnalyses: AlertAnalysis[] = [
  {
    id: 'analysis-1',
    alert_id: 'alert-123',
    tenant_id: 'tenant-1',
    status: 'completed',
    started_at: '2025-01-15T10:00:00Z',
    completed_at: '2025-01-15T10:05:00Z',
    created_at: '2025-01-15T10:00:00Z',
    updated_at: '2025-01-15T10:05:00Z',
    steps_progress: {},
    workflow_run_id: 'workflow-1',
  },
  {
    id: 'analysis-2',
    alert_id: 'alert-123',
    tenant_id: 'tenant-1',
    status: 'failed',
    started_at: '2025-01-14T10:00:00Z',
    created_at: '2025-01-14T10:00:00Z',
    updated_at: '2025-01-14T10:05:00Z',
    steps_progress: {},
    error_message: 'Analysis failed',
  },
];

describe('AnalysisRunSelector', () => {
  it('should render the selector with selected analysis', () => {
    const onSelect = vi.fn();

    render(
      <AnalysisRunSelector analyses={mockAnalyses} selectedId="analysis-1" onSelect={onSelect} />
    );

    // Should show Latest label for newest analysis
    expect(screen.getByText(/Latest/)).toBeInTheDocument();
    expect(screen.getByText(/Completed/)).toBeInTheDocument();
  });

  it('should show empty state when no analyses', () => {
    const onSelect = vi.fn();

    render(<AnalysisRunSelector analyses={[]} selectedId="" onSelect={onSelect} />);

    expect(screen.getByText('No analysis runs available')).toBeInTheDocument();
  });

  it('should call onSelect when clicking an option', () => {
    const onSelect = vi.fn();

    render(
      <AnalysisRunSelector analyses={mockAnalyses} selectedId="analysis-1" onSelect={onSelect} />
    );

    // Click to open dropdown
    const button = screen.getByRole('button');
    fireEvent.click(button);

    // Should show both options
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(2);

    // Click on the second option (failed analysis)
    fireEvent.click(options[1]);

    expect(onSelect).toHaveBeenCalledWith('analysis-2');
  });

  it('should sort analyses by date (newest first)', () => {
    const onSelect = vi.fn();

    render(
      <AnalysisRunSelector analyses={mockAnalyses} selectedId="analysis-1" onSelect={onSelect} />
    );

    // Open dropdown
    const button = screen.getByRole('button');
    fireEvent.click(button);

    const options = screen.getAllByRole('option');

    // First option should be the latest (analysis-1)
    expect(options[0]).toHaveTextContent('Latest');
    expect(options[0]).toHaveTextContent('Completed');

    // Second option should be the older one (analysis-2)
    expect(options[1]).toHaveTextContent('Run 1');
    expect(options[1]).toHaveTextContent('Failed');
  });

  it('should be disabled when disabled prop is true', () => {
    const onSelect = vi.fn();

    render(
      <AnalysisRunSelector
        analyses={mockAnalyses}
        selectedId="analysis-1"
        onSelect={onSelect}
        disabled={true}
      />
    );

    const button = screen.getByRole('button');
    expect(button).toHaveClass('disabled:opacity-50');
  });
});
