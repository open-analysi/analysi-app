import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { backendApi } from '../../../services/backendApi';
import type {
  AlertRoutingRuleListResponse,
  AnalysisGroupListResponse,
} from '../../../types/settings';
import type { WorkflowsResponse } from '../../../types/workflow';
import { AlertRoutingRules } from '../AlertRoutingRules';

vi.mock('../../../services/backendApi');

describe('AlertRoutingRules', () => {
  const WORKFLOW_1_ID = 'workflow-1';
  const SOC170_TITLE = 'SOC170 - LFI Attack';

  const mockRules: AlertRoutingRuleListResponse = {
    rules: [
      {
        id: 'rule-1',
        tenant_id: 'tenant-1',
        analysis_group_id: 'group-1',
        workflow_id: WORKFLOW_1_ID,
        created_at: '2025-12-09T05:24:04.582105Z',
      },
      {
        id: 'rule-2',
        tenant_id: 'tenant-1',
        analysis_group_id: 'group-2',
        workflow_id: 'workflow-2',
        created_at: '2025-12-09T03:20:18.506245Z',
      },
    ],
    total: 2,
  };

  const mockAnalysisGroups: AnalysisGroupListResponse = {
    analysis_groups: [
      {
        id: 'group-1',
        tenant_id: 'tenant-1',
        title: SOC170_TITLE,
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

  const mockWorkflows: WorkflowsResponse = {
    workflows: [
      {
        id: WORKFLOW_1_ID,
        tenant_id: 'test-tenant',
        name: 'SOC170 Analysis Workflow',
        description: 'Test workflow',
        is_dynamic: false,
        io_schema: { input: {}, output: {} },
        status: 'active',
        created_at: '2025-12-09T00:00:00.000Z',
        created_by: 'test-user',
        planner_id: null,
        nodes: [],
        edges: [],
      },
      {
        id: 'workflow-2',
        tenant_id: 'test-tenant',
        name: 'SOC166 Analysis Workflow',
        description: 'Test workflow 2',
        is_dynamic: false,
        io_schema: { input: {}, output: {} },
        status: 'active',
        created_at: '2025-12-09T00:00:00.000Z',
        created_by: 'test-user',
        planner_id: null,
        nodes: [],
        edges: [],
      },
    ],
    total: 2,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the component with header', () => {
    vi.mocked(backendApi.getAlertRoutingRules).mockResolvedValue(mockRules);
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue(mockAnalysisGroups);
    vi.mocked(backendApi.getWorkflows).mockResolvedValue(mockWorkflows);

    render(<AlertRoutingRules />);

    expect(screen.getByText('Alert Routing Rules')).toBeInTheDocument();
    expect(
      screen.getByText('Map analysis groups to workflows for automated alert processing')
    ).toBeInTheDocument();
  });

  it('displays loading state initially', () => {
    vi.mocked(backendApi.getAlertRoutingRules).mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue(mockAnalysisGroups);
    vi.mocked(backendApi.getWorkflows).mockResolvedValue(mockWorkflows);

    render(<AlertRoutingRules />);

    expect(screen.getByText('Loading routing rules...')).toBeInTheDocument();
  });

  it('displays alert routing rules after loading', async () => {
    vi.mocked(backendApi.getAlertRoutingRules).mockResolvedValue(mockRules);
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue(mockAnalysisGroups);
    vi.mocked(backendApi.getWorkflows).mockResolvedValue(mockWorkflows);

    render(<AlertRoutingRules />);

    await waitFor(() => {
      expect(screen.getByText(SOC170_TITLE)).toBeInTheDocument();
      expect(screen.getByText('SOC170 Analysis Workflow')).toBeInTheDocument();
      expect(screen.getByText('SOC166 - Javascript Code Detected')).toBeInTheDocument();
      expect(screen.getByText('SOC166 Analysis Workflow')).toBeInTheDocument();
    });

    expect(screen.getByText('Showing 2 routing rules')).toBeInTheDocument();
  });

  it('displays empty state when no rules exist', async () => {
    vi.mocked(backendApi.getAlertRoutingRules).mockResolvedValue({
      rules: [],
      total: 0,
    });
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue(mockAnalysisGroups);
    vi.mocked(backendApi.getWorkflows).mockResolvedValue(mockWorkflows);

    render(<AlertRoutingRules />);

    await waitFor(() => {
      expect(
        screen.getByText('No routing rules found. Create one to get started.')
      ).toBeInTheDocument();
    });
  });

  it('shows create form when New Rule button is clicked', async () => {
    const user = userEvent.setup();
    vi.mocked(backendApi.getAlertRoutingRules).mockResolvedValue(mockRules);
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue(mockAnalysisGroups);
    vi.mocked(backendApi.getWorkflows).mockResolvedValue(mockWorkflows);

    render(<AlertRoutingRules />);

    await waitFor(() => {
      expect(screen.getByText(SOC170_TITLE)).toBeInTheDocument();
    });

    const newRuleButton = screen.getByRole('button', { name: /new rule/i });
    await user.click(newRuleButton);

    expect(screen.getByText('Create New Routing Rule')).toBeInTheDocument();
    expect(screen.getByLabelText('Analysis Group')).toBeInTheDocument();
    expect(screen.getByLabelText('Workflow')).toBeInTheDocument();
  });

  it('creates a new routing rule', async () => {
    const user = userEvent.setup();
    const newRule = {
      id: 'rule-3',
      tenant_id: 'tenant-1',
      analysis_group_id: 'group-1',
      workflow_id: WORKFLOW_1_ID,
      created_at: '2025-12-10T00:00:00.000Z',
    };

    vi.mocked(backendApi.getAlertRoutingRules)
      .mockResolvedValueOnce(mockRules)
      .mockResolvedValueOnce({
        rules: [...mockRules.rules, newRule],
        total: 3,
      });

    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue(mockAnalysisGroups);
    vi.mocked(backendApi.getWorkflows).mockResolvedValue(mockWorkflows);
    vi.mocked(backendApi.createAlertRoutingRule).mockResolvedValue(newRule);

    render(<AlertRoutingRules />);

    await waitFor(() => {
      expect(screen.getByText(SOC170_TITLE)).toBeInTheDocument();
    });

    // Open create form
    const newRuleButton = screen.getByRole('button', { name: /new rule/i });
    await user.click(newRuleButton);

    // Select analysis group
    const groupSelect = screen.getByLabelText('Analysis Group');
    await user.selectOptions(groupSelect, 'group-1');

    // Select workflow
    const workflowSelect = screen.getByLabelText('Workflow');
    await user.selectOptions(workflowSelect, WORKFLOW_1_ID);

    // Submit
    const createButton = screen.getByRole('button', { name: /^create$/i });
    await user.click(createButton);

    await waitFor(() => {
      expect(backendApi.createAlertRoutingRule).toHaveBeenCalledWith({
        analysis_group_id: 'group-1',
        workflow_id: WORKFLOW_1_ID,
      });
    });

    // Verify form is closed and data is reloaded
    await waitFor(() => {
      expect(screen.queryByText('Create New Routing Rule')).not.toBeInTheDocument();
    });
  });

  it('create button is disabled when selections are incomplete', async () => {
    const user = userEvent.setup();
    vi.mocked(backendApi.getAlertRoutingRules).mockResolvedValue(mockRules);
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue(mockAnalysisGroups);
    vi.mocked(backendApi.getWorkflows).mockResolvedValue(mockWorkflows);

    render(<AlertRoutingRules />);

    await waitFor(() => {
      expect(screen.getByText(SOC170_TITLE)).toBeInTheDocument();
    });

    // Open create form
    const newRuleButton = screen.getByRole('button', { name: /new rule/i });
    await user.click(newRuleButton);

    const createButton = screen.getByRole('button', { name: /^create$/i });
    expect(createButton).toBeDisabled();

    // Select only analysis group
    const groupSelect = screen.getByLabelText('Analysis Group');
    await user.selectOptions(groupSelect, 'group-1');

    // Should still be disabled
    expect(createButton).toBeDisabled();

    // Select workflow
    const workflowSelect = screen.getByLabelText('Workflow');
    await user.selectOptions(workflowSelect, WORKFLOW_1_ID);

    // Should now be enabled
    expect(createButton).not.toBeDisabled();
  });

  it('cancels create form', async () => {
    const user = userEvent.setup();
    vi.mocked(backendApi.getAlertRoutingRules).mockResolvedValue(mockRules);
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue(mockAnalysisGroups);
    vi.mocked(backendApi.getWorkflows).mockResolvedValue(mockWorkflows);

    render(<AlertRoutingRules />);

    await waitFor(() => {
      expect(screen.getByText(SOC170_TITLE)).toBeInTheDocument();
    });

    // Open create form
    const newRuleButton = screen.getByRole('button', { name: /new rule/i });
    await user.click(newRuleButton);

    expect(screen.getByText('Create New Routing Rule')).toBeInTheDocument();

    // Click cancel
    const cancelButton = screen.getByRole('button', { name: /cancel/i });
    await user.click(cancelButton);

    expect(screen.queryByText('Create New Routing Rule')).not.toBeInTheDocument();
  });

  it('refreshes data when refresh button is clicked', async () => {
    const user = userEvent.setup();
    vi.mocked(backendApi.getAlertRoutingRules).mockResolvedValue(mockRules);
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue(mockAnalysisGroups);
    vi.mocked(backendApi.getWorkflows).mockResolvedValue(mockWorkflows);

    render(<AlertRoutingRules />);

    await waitFor(() => {
      expect(screen.getByText(SOC170_TITLE)).toBeInTheDocument();
    });

    const refreshButton = screen.getByRole('button', { name: /refresh/i });
    await user.click(refreshButton);

    // Should call the API again
    await waitFor(() => {
      expect(backendApi.getAlertRoutingRules).toHaveBeenCalledTimes(2);
    });
  });

  it('displays Unknown Group when analysis group not found', async () => {
    const rulesWithUnknownGroup: AlertRoutingRuleListResponse = {
      rules: [
        {
          id: 'rule-1',
          tenant_id: 'tenant-1',
          analysis_group_id: 'unknown-group',
          workflow_id: WORKFLOW_1_ID,
          created_at: '2025-12-09T05:24:04.582105Z',
        },
      ],
      total: 1,
    };

    vi.mocked(backendApi.getAlertRoutingRules).mockResolvedValue(rulesWithUnknownGroup);
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue(mockAnalysisGroups);
    vi.mocked(backendApi.getWorkflows).mockResolvedValue(mockWorkflows);

    render(<AlertRoutingRules />);

    await waitFor(() => {
      expect(screen.getByText('Unknown Group')).toBeInTheDocument();
    });
  });

  it('displays Unknown Workflow when workflow not found', async () => {
    const rulesWithUnknownWorkflow: AlertRoutingRuleListResponse = {
      rules: [
        {
          id: 'rule-1',
          tenant_id: 'tenant-1',
          analysis_group_id: 'group-1',
          workflow_id: 'unknown-workflow',
          created_at: '2025-12-09T05:24:04.582105Z',
        },
      ],
      total: 1,
    };

    vi.mocked(backendApi.getAlertRoutingRules).mockResolvedValue(rulesWithUnknownWorkflow);
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue(mockAnalysisGroups);
    vi.mocked(backendApi.getWorkflows).mockResolvedValue(mockWorkflows);

    render(<AlertRoutingRules />);

    await waitFor(() => {
      expect(screen.getByText('Unknown Workflow')).toBeInTheDocument();
    });
  });

  it('displays count correctly for singular rule', async () => {
    vi.mocked(backendApi.getAlertRoutingRules).mockResolvedValue({
      rules: [mockRules.rules[0]],
      total: 1,
    });
    vi.mocked(backendApi.getAnalysisGroups).mockResolvedValue(mockAnalysisGroups);
    vi.mocked(backendApi.getWorkflows).mockResolvedValue(mockWorkflows);

    render(<AlertRoutingRules />);

    await waitFor(() => {
      expect(screen.getByText('Showing 1 routing rule')).toBeInTheDocument();
    });
  });
});
