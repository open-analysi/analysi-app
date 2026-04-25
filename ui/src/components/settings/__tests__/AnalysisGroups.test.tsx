import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { backendApi } from '../../../services/backendApi';
import type { AnalysisGroupListResponse } from '../../../types/settings';
import { AnalysisGroups } from '../AnalysisGroups';

vi.mock('../../../services/backendApi');

describe('AnalysisGroups', () => {
  const mockAnalysisGroups: AnalysisGroupListResponse = {
    analysis_groups: [
      {
        id: 'group-1',
        tenant_id: 'tenant-1',
        title: 'SOC170 - LFI Attack',
        created_at: '2025-12-09T05:24:04.582105Z',
      },
      {
        id: 'group-2',
        tenant_id: 'tenant-1',
        title: 'SOC166 - Javascript Code Detected',
        created_at: '2025-12-09T03:20:18.506245Z',
      },
    ],
    total: 2,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the component with header', () => {
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue(mockAnalysisGroups);

    render(<AnalysisGroups />);

    expect(screen.getByText('Analysis Groups')).toBeInTheDocument();
    expect(
      screen.getByText('Manage analysis groups that categorize alerts by rule name')
    ).toBeInTheDocument();
  });

  it('displays loading state initially', () => {
    vi.mocked(backendApi.getAnalysisGroups).mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );

    render(<AnalysisGroups />);

    expect(screen.getByText('Loading analysis groups...')).toBeInTheDocument();
  });

  it('displays analysis groups after loading', async () => {
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue(mockAnalysisGroups);

    render(<AnalysisGroups />);

    await waitFor(() => {
      expect(screen.getByText('SOC170 - LFI Attack')).toBeInTheDocument();
      expect(screen.getByText('SOC166 - Javascript Code Detected')).toBeInTheDocument();
    });

    expect(screen.getByText('Showing 2 analysis groups')).toBeInTheDocument();
  });

  it('displays empty state when no groups exist', async () => {
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue({
      analysis_groups: [],
      total: 0,
    });

    render(<AnalysisGroups />);

    await waitFor(() => {
      expect(
        screen.getByText('No analysis groups found. Create one to get started.')
      ).toBeInTheDocument();
    });
  });

  it('shows create form when New Group button is clicked', async () => {
    const user = userEvent.setup();
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue(mockAnalysisGroups);

    render(<AnalysisGroups />);

    await waitFor(() => {
      expect(screen.getByText('SOC170 - LFI Attack')).toBeInTheDocument();
    });

    const newGroupButton = screen.getByRole('button', { name: /new group/i });
    await user.click(newGroupButton);

    expect(screen.getByText('Create New Analysis Group')).toBeInTheDocument();
    expect(screen.getByLabelText('Title (Rule Name)')).toBeInTheDocument();
  });

  it('creates a new analysis group', async () => {
    const user = userEvent.setup();
    const newGroup = {
      id: 'group-3',
      tenant_id: 'tenant-1',
      title: 'New Test Group',
      created_at: '2025-12-10T00:00:00.000Z',
    };

    vi.mocked(backendApi.getAnalysisGroups)
      .mockResolvedValueOnce(mockAnalysisGroups)
      .mockResolvedValueOnce({
        analysis_groups: [...mockAnalysisGroups.analysis_groups, newGroup],
        total: 3,
      });

    vi.mocked(backendApi.createAnalysisGroup).mockResolvedValue(newGroup);

    render(<AnalysisGroups />);

    await waitFor(() => {
      expect(screen.getByText('SOC170 - LFI Attack')).toBeInTheDocument();
    });

    // Open create form
    const newGroupButton = screen.getByRole('button', { name: /new group/i });
    await user.click(newGroupButton);

    // Fill in the form
    const titleInput = screen.getByLabelText('Title (Rule Name)');
    await user.type(titleInput, 'New Test Group');

    // Submit
    const createButton = screen.getByRole('button', { name: /^create$/i });
    await user.click(createButton);

    await waitFor(() => {
      expect(backendApi.createAnalysisGroup).toHaveBeenCalledWith({
        title: 'New Test Group',
      });
    });

    // Verify form is closed and data is reloaded
    await waitFor(() => {
      expect(screen.queryByText('Create New Analysis Group')).not.toBeInTheDocument();
    });
  });

  it('cancels create form', async () => {
    const user = userEvent.setup();
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue(mockAnalysisGroups);

    render(<AnalysisGroups />);

    await waitFor(() => {
      expect(screen.getByText('SOC170 - LFI Attack')).toBeInTheDocument();
    });

    // Open create form
    const newGroupButton = screen.getByRole('button', { name: /new group/i });
    await user.click(newGroupButton);

    expect(screen.getByText('Create New Analysis Group')).toBeInTheDocument();

    // Click cancel
    const cancelButton = screen.getByRole('button', { name: /cancel/i });
    await user.click(cancelButton);

    expect(screen.queryByText('Create New Analysis Group')).not.toBeInTheDocument();
  });

  it('refreshes data when refresh button is clicked', async () => {
    const user = userEvent.setup();
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue(mockAnalysisGroups);

    render(<AnalysisGroups />);

    await waitFor(() => {
      expect(screen.getByText('SOC170 - LFI Attack')).toBeInTheDocument();
    });

    const refreshButton = screen.getByRole('button', { name: /refresh/i });
    await user.click(refreshButton);

    // Should call the API again
    await waitFor(() => {
      expect(backendApi.getAnalysisGroups).toHaveBeenCalledTimes(2);
    });
  });

  it('formats dates correctly', async () => {
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue(mockAnalysisGroups);

    render(<AnalysisGroups />);

    await waitFor(() => {
      // Check for formatted date (format: "Dec 9, 2025, 05:24 AM" or similar)
      const dates = screen.getAllByText(/Dec \d+, 2025/);
      expect(dates.length).toBeGreaterThan(0);
    });
  });

  it('displays count correctly for singular group', async () => {
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue({
      analysis_groups: [mockAnalysisGroups.analysis_groups[0]],
      total: 1,
    });

    render(<AnalysisGroups />);

    await waitFor(() => {
      expect(screen.getByText('Showing 1 analysis group')).toBeInTheDocument();
    });
  });
});
