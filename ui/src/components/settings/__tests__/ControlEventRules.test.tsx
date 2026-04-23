import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { backendApi } from '../../../services/backendApi';
import type { ControlEventChannel, ControlEventRule } from '../../../types/controlEvents';
import type { Task } from '../../../types/knowledge';
import type { Workflow } from '../../../types/workflow';
import { ControlEventRules } from '../ControlEventRules';

vi.mock('../../../services/backendApi');

const CH_DISPOSITION_READY = 'disposition:ready';
const RULE_NAME_NOTIFY = 'Notify on Disposition';

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

const mockTasks: Task[] = [
  { id: 'task-1', name: 'Slack Notify', description: '', cy_name: 'slack_notify' } as Task,
  { id: 'task-2', name: 'Email Alert', description: '', cy_name: 'email_alert' } as Task,
];

const mockWorkflows: Workflow[] = [{ id: 'wf-1', name: 'Triage Pipeline' } as Workflow];

const mockRules: ControlEventRule[] = [
  {
    id: 'rule-1',
    tenant_id: 't-1',
    name: RULE_NAME_NOTIFY,
    channel: CH_DISPOSITION_READY,
    target_type: 'task',
    target_id: 'task-1',
    enabled: true,
    config: {},
    created_at: '2025-12-01T00:00:00Z',
    updated_at: '2025-12-01T00:00:00Z',
  },
  {
    id: 'rule-2',
    tenant_id: 't-1',
    name: 'Auto-triage new alerts',
    channel: 'alert:created',
    target_type: 'workflow',
    target_id: 'wf-1',
    enabled: false,
    config: { priority: 'high' },
    created_at: '2025-12-02T00:00:00Z',
    updated_at: '2025-12-02T00:00:00Z',
  },
];

function setupMocks(rules = mockRules) {
  vi.mocked(backendApi.getControlEventRules).mockResolvedValue({ rules, total: rules.length });
  vi.mocked(backendApi.getControlEventChannels).mockResolvedValue({
    channels: mockChannels,
    total: mockChannels.length,
  });
  vi.mocked(backendApi.getTasks).mockResolvedValue({ tasks: mockTasks, total: mockTasks.length });
  vi.mocked(backendApi.getWorkflows).mockResolvedValue({
    workflows: mockWorkflows,
    total: mockWorkflows.length,
  });
}

function renderComponent() {
  return render(
    <MemoryRouter>
      <ControlEventRules />
    </MemoryRouter>
  );
}

describe('ControlEventRules', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders header and action buttons', () => {
    setupMocks();
    renderComponent();

    expect(screen.getByText('Event Reaction Rules')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /refresh/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /new rule/i })).toBeInTheDocument();
  });

  it('displays loading state initially', () => {
    vi.mocked(backendApi.getControlEventRules).mockImplementation(() => new Promise(() => {}));
    vi.mocked(backendApi.getControlEventChannels).mockImplementation(() => new Promise(() => {}));
    vi.mocked(backendApi.getTasks).mockImplementation(() => new Promise(() => {}));
    vi.mocked(backendApi.getWorkflows).mockImplementation(() => new Promise(() => {}));

    renderComponent();

    expect(screen.getByText('Loading rules…')).toBeInTheDocument();
  });

  it('displays rules in table after loading', async () => {
    setupMocks();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(RULE_NAME_NOTIFY)).toBeInTheDocument();
      expect(screen.getByText('Auto-triage new alerts')).toBeInTheDocument();
    });

    expect(screen.getByText('2 rules')).toBeInTheDocument();
  });

  it('displays empty state when no rules exist', async () => {
    setupMocks([]);
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('No reaction rules yet.')).toBeInTheDocument();
    });
  });

  it('shows channel badges for rules', async () => {
    setupMocks();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(CH_DISPOSITION_READY)).toBeInTheDocument();
      expect(screen.getByText('alert:created')).toBeInTheDocument();
    });
  });

  it('resolves target names via loaded tasks/workflows', async () => {
    setupMocks();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Slack Notify')).toBeInTheDocument();
      expect(screen.getByText('Triage Pipeline')).toBeInTheDocument();
    });
  });

  it('shows create form when New Rule button is clicked', async () => {
    const user = userEvent.setup();
    setupMocks();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(RULE_NAME_NOTIFY)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /new rule/i }));

    expect(screen.getByText('Create New Rule')).toBeInTheDocument();
    expect(screen.getByLabelText('Name')).toBeInTheDocument();
    expect(screen.getByLabelText('Channel')).toBeInTheDocument();
  });

  it('shows Edit Rule title when editing an existing rule', async () => {
    const user = userEvent.setup();
    setupMocks();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(RULE_NAME_NOTIFY)).toBeInTheDocument();
    });

    const editButtons = screen.getAllByTitle('Edit rule');
    await user.click(editButtons[0]);

    expect(screen.getByText('Edit Rule')).toBeInTheDocument();
    // Form should be pre-filled
    expect(screen.getByLabelText('Name')).toHaveValue(RULE_NAME_NOTIFY);
  });

  it('cancels form when Cancel button is clicked', async () => {
    const user = userEvent.setup();
    setupMocks();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(RULE_NAME_NOTIFY)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /new rule/i }));
    expect(screen.getByText('Create New Rule')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByText('Create New Rule')).not.toBeInTheDocument();
  });

  it('creates a new rule and reloads data', async () => {
    const user = userEvent.setup();
    setupMocks();
    vi.mocked(backendApi.createControlEventRule).mockResolvedValue({
      id: 'rule-3',
      tenant_id: 't-1',
      name: 'New Rule',
      channel: CH_DISPOSITION_READY,
      target_type: 'task',
      target_id: 'task-1',
      enabled: true,
      config: {},
      created_at: '2025-12-03T00:00:00Z',
      updated_at: '2025-12-03T00:00:00Z',
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(RULE_NAME_NOTIFY)).toBeInTheDocument();
    });

    // Open form
    await user.click(screen.getByRole('button', { name: /new rule/i }));

    // Fill form
    await user.type(screen.getByLabelText('Name'), 'New Rule');
    await user.selectOptions(screen.getByLabelText('Channel'), CH_DISPOSITION_READY);
    await user.selectOptions(screen.getByLabelText(/Target Task/), 'task-1');

    // Save
    await user.click(screen.getByRole('button', { name: /create rule/i }));

    await waitFor(() => {
      expect(backendApi.createControlEventRule).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'New Rule',
          channel: CH_DISPOSITION_READY,
          target_type: 'task',
          target_id: 'task-1',
          enabled: true,
        })
      );
    });
  });

  it('validates JSON config and shows error for invalid JSON', async () => {
    const user = userEvent.setup();
    setupMocks();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(RULE_NAME_NOTIFY)).toBeInTheDocument();
    });

    // Open form
    await user.click(screen.getByRole('button', { name: /new rule/i }));

    // Fill required fields
    await user.type(screen.getByLabelText('Name'), 'Bad Config Rule');
    await user.selectOptions(screen.getByLabelText('Channel'), CH_DISPOSITION_READY);
    await user.selectOptions(screen.getByLabelText(/Target Task/), 'task-1');

    // Type invalid JSON
    const configTextarea = screen.getByLabelText(/Config/);
    await user.clear(configTextarea);
    await user.type(configTextarea, '{{invalid json');

    // Try to save
    await user.click(screen.getByRole('button', { name: /create rule/i }));

    await waitFor(() => {
      expect(screen.getByText(/Invalid JSON/)).toBeInTheDocument();
    });

    // Should NOT have called the API
    expect(backendApi.createControlEventRule).not.toHaveBeenCalled();
  });

  it('toggles enabled state optimistically', async () => {
    const user = userEvent.setup();
    setupMocks();
    vi.mocked(backendApi.updateControlEventRule).mockResolvedValue(mockRules[0]);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(RULE_NAME_NOTIFY)).toBeInTheDocument();
    });

    // Find the enabled toggle for rule-1 (currently enabled)
    const toggles = screen.getAllByRole('button', { pressed: true });
    expect(toggles.length).toBeGreaterThan(0);

    await user.click(toggles[0]);

    await waitFor(() => {
      expect(backendApi.updateControlEventRule).toHaveBeenCalledWith('rule-1', { enabled: false });
    });
  });

  it('reverts toggle on API error', async () => {
    const user = userEvent.setup();
    setupMocks();
    vi.mocked(backendApi.updateControlEventRule).mockRejectedValue(new Error('Network error'));

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(RULE_NAME_NOTIFY)).toBeInTheDocument();
    });

    const toggles = screen.getAllByRole('button', { pressed: true });
    await user.click(toggles[0]);

    // After error, should still show as enabled (reverted)
    await waitFor(() => {
      const enabledToggles = screen.getAllByRole('button', { pressed: true });
      expect(enabledToggles.length).toBeGreaterThan(0);
    });
  });

  it('deletes a rule after confirmation', async () => {
    const user = userEvent.setup();
    setupMocks();
    vi.mocked(backendApi.deleteControlEventRule).mockResolvedValue(undefined);

    // Mock window.confirm
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(RULE_NAME_NOTIFY)).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByTitle('Delete rule');
    await user.click(deleteButtons[0]);

    expect(confirmSpy).toHaveBeenCalled();

    await waitFor(() => {
      expect(backendApi.deleteControlEventRule).toHaveBeenCalledWith('rule-1');
    });

    confirmSpy.mockRestore();
  });

  it('does not delete when confirmation is cancelled', async () => {
    const user = userEvent.setup();
    setupMocks();

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(RULE_NAME_NOTIFY)).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByTitle('Delete rule');
    await user.click(deleteButtons[0]);

    expect(confirmSpy).toHaveBeenCalled();
    expect(backendApi.deleteControlEventRule).not.toHaveBeenCalled();

    confirmSpy.mockRestore();
  });

  it('refreshes data when refresh button is clicked', async () => {
    const user = userEvent.setup();
    setupMocks();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(RULE_NAME_NOTIFY)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /refresh/i }));

    await waitFor(() => {
      expect(backendApi.getControlEventRules).toHaveBeenCalledTimes(2);
    });
  });

  it('switches target options when target type changes', async () => {
    const user = userEvent.setup();
    setupMocks();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(RULE_NAME_NOTIFY)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /new rule/i }));

    // Default is 'task' — should see task options
    expect(screen.getByLabelText(/Target Task/)).toBeInTheDocument();

    // Switch to workflow
    await user.click(screen.getByLabelText('workflow'));
    expect(screen.getByLabelText(/Target Workflow/)).toBeInTheDocument();
  });

  it('disables save when required fields are empty', async () => {
    const user = userEvent.setup();
    setupMocks();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(RULE_NAME_NOTIFY)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /new rule/i }));

    // Save button should be disabled with empty form
    const saveButton = screen.getByRole('button', { name: /create rule/i });
    expect(saveButton).toBeDisabled();
  });
});
