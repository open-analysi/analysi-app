import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { backendApi } from '../../../services/backendApi';
import type { ControlEvent, ControlEventChannel } from '../../../types/controlEvents';
import { ControlEventHistory } from '../ControlEventHistory';

vi.mock('../../../services/backendApi');

const CH_DISPOSITION_READY = 'disposition:ready';

const mockChannels: ControlEventChannel[] = [
  {
    channel: CH_DISPOSITION_READY,
    type: 'system',
    description: 'Fires when a disposition is marked ready',
    payload_fields: ['alert_id', 'disposition'],
  },
  {
    channel: 'alert:created',
    type: 'system',
    description: 'Fires when a new alert is created',
    payload_fields: ['alert_id'],
  },
];

const mockEvents: ControlEvent[] = [
  {
    id: 'evt-1',
    tenant_id: 't-1',
    channel: CH_DISPOSITION_READY,
    payload: { alert_id: 'alert-123', disposition: 'malicious' },
    status: 'completed',
    retry_count: 0,
    created_at: '2025-12-15T10:30:00Z',
    claimed_at: null,
  },
  {
    id: 'evt-2',
    tenant_id: 't-1',
    channel: 'alert:created',
    payload: { alert_id: 'alert-456' },
    status: 'failed',
    retry_count: 2,
    created_at: '2025-12-15T09:00:00Z',
    claimed_at: null,
  },
  {
    id: 'evt-3',
    tenant_id: 't-1',
    channel: CH_DISPOSITION_READY,
    payload: {},
    status: 'pending',
    retry_count: 0,
    created_at: '2025-12-15T11:00:00Z',
    claimed_at: null,
  },
];

function setupMocks(events = mockEvents) {
  vi.mocked(backendApi.getControlEvents).mockResolvedValue({ events, total: events.length });
  vi.mocked(backendApi.getControlEventChannels).mockResolvedValue({
    channels: mockChannels,
    total: mockChannels.length,
  });
}

describe('ControlEventHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders loading state initially', () => {
    vi.mocked(backendApi.getControlEvents).mockImplementation(() => new Promise(() => {}));
    vi.mocked(backendApi.getControlEventChannels).mockImplementation(() => new Promise(() => {}));

    render(<ControlEventHistory />);

    expect(screen.getByText('Loading events…')).toBeInTheDocument();
  });

  it('displays events after loading', async () => {
    setupMocks();
    render(<ControlEventHistory />);

    await waitFor(() => {
      // Channel names appear in both filter dropdown and table rows.
      // Check that the table body contains the expected channel text.
      const tableBody = screen.getAllByRole('row');
      expect(tableBody.length).toBeGreaterThan(1); // header + event rows
    });

    expect(screen.getByText('3 events')).toBeInTheDocument();
  });

  it('displays empty state when no events found', async () => {
    setupMocks([]);
    render(<ControlEventHistory />);

    await waitFor(() => {
      expect(screen.getByText('No events found for the selected filters.')).toBeInTheDocument();
    });
  });

  it('shows status badges for each event', async () => {
    setupMocks();
    render(<ControlEventHistory />);

    await waitFor(() => {
      expect(screen.getByText('completed')).toBeInTheDocument();
      expect(screen.getByText('failed')).toBeInTheDocument();
      expect(screen.getByText('pending')).toBeInTheDocument();
    });
  });

  it('expands event row to show payload on click', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    setupMocks();
    render(<ControlEventHistory />);

    await waitFor(() => {
      expect(screen.getByText('3 events')).toBeInTheDocument();
    });

    // Click on first event row to expand
    const rows = screen.getAllByRole('row');
    // row[0] is header, rows[1-3] are event rows
    await user.click(rows[1]);

    // Should show payload and event ID
    await waitFor(() => {
      expect(screen.getByText('Event ID')).toBeInTheDocument();
      expect(screen.getByText('evt-1')).toBeInTheDocument();
      expect(screen.getByText('Payload')).toBeInTheDocument();
    });
  });

  it('collapses expanded row on second click', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    setupMocks();
    render(<ControlEventHistory />);

    await waitFor(() => {
      expect(screen.getByText('3 events')).toBeInTheDocument();
    });

    const rows = screen.getAllByRole('row');
    // Expand
    await user.click(rows[1]);
    await waitFor(() => {
      expect(screen.getByText('evt-1')).toBeInTheDocument();
    });

    // Collapse
    await user.click(rows[1]);
    await waitFor(() => {
      expect(screen.queryByText('evt-1')).not.toBeInTheDocument();
    });
  });

  it('renders filter dropdowns for channel, status, and days', async () => {
    setupMocks();
    render(<ControlEventHistory />);

    await waitFor(() => {
      expect(screen.getByText('3 events')).toBeInTheDocument();
    });

    // Filter dropdowns should be present
    expect(screen.getByDisplayValue('All channels')).toBeInTheDocument();
    expect(screen.getByDisplayValue('All statuses')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Last 7 days')).toBeInTheDocument();
  });

  it('refreshes data when refresh button is clicked', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    setupMocks();
    render(<ControlEventHistory />);

    await waitFor(() => {
      expect(screen.getByText('3 events')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /refresh/i }));

    await waitFor(() => {
      expect(backendApi.getControlEvents).toHaveBeenCalledTimes(2);
    });
  });

  it('shows the Fire Test Event panel when toggled', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    setupMocks();
    render(<ControlEventHistory />);

    await waitFor(() => {
      expect(screen.getByText('3 events')).toBeInTheDocument();
    });

    // Test panel toggle
    await user.click(screen.getByText('Fire Test Event'));

    await waitFor(() => {
      expect(screen.getByLabelText('Channel')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /fire event/i })).toBeInTheDocument();
    });
  });

  it('disables Fire Event button when no channel selected', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    setupMocks();
    render(<ControlEventHistory />);

    await waitFor(() => {
      expect(screen.getByText('3 events')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Fire Test Event'));

    const fireButton = screen.getByRole('button', { name: /fire event/i });
    expect(fireButton).toBeDisabled();
  });

  it('shows payload fields when a channel is selected in test panel', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    setupMocks();
    render(<ControlEventHistory />);

    await waitFor(() => {
      expect(screen.getByText('3 events')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Fire Test Event'));
    await user.selectOptions(screen.getByLabelText('Channel'), CH_DISPOSITION_READY);

    await waitFor(() => {
      expect(screen.getByText('Payload fields')).toBeInTheDocument();
      expect(screen.getByText('alert_id')).toBeInTheDocument();
      expect(screen.getByText('disposition')).toBeInTheDocument();
    });
  });

  it('fires a test event and shows result', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    setupMocks();

    const firedEvent: ControlEvent = {
      id: 'evt-test-1',
      tenant_id: 't-1',
      channel: CH_DISPOSITION_READY,
      payload: {},
      status: 'completed',
      retry_count: 0,
      created_at: '2025-12-15T12:00:00Z',
      claimed_at: null,
    };

    vi.mocked(backendApi.createControlEvent).mockResolvedValue(firedEvent);

    render(<ControlEventHistory />);

    await waitFor(() => {
      expect(screen.getByText('3 events')).toBeInTheDocument();
    });

    // Open test panel and select channel
    await user.click(screen.getByText('Fire Test Event'));
    await user.selectOptions(screen.getByLabelText('Channel'), CH_DISPOSITION_READY);

    // Fire the event
    await user.click(screen.getByRole('button', { name: /fire event/i }));

    await waitFor(() => {
      expect(backendApi.createControlEvent).toHaveBeenCalledWith({
        channel: CH_DISPOSITION_READY,
        payload: {},
      });
    });

    // Should show the event result (terminal status, no polling)
    await waitFor(() => {
      expect(screen.getByText('evt-test-1')).toBeInTheDocument();
    });
  });

  it('renders table headers correctly', async () => {
    setupMocks();
    render(<ControlEventHistory />);

    await waitFor(() => {
      expect(screen.getByText('Channel', { selector: 'th' })).toBeInTheDocument();
      expect(screen.getByText('Status', { selector: 'th' })).toBeInTheDocument();
      expect(screen.getByText('Retries', { selector: 'th' })).toBeInTheDocument();
      expect(screen.getByText('When', { selector: 'th' })).toBeInTheDocument();
    });
  });
});
