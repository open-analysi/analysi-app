/* eslint-disable sonarjs/no-duplicate-string */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import type { Alert } from '../../../types/alert';
import type { Artifact } from '../../../types/artifact';
import type { TaskRun } from '../../../types/taskRun';
import { OverviewTab } from '../OverviewTab';

// Wrap component with router since OverviewTab uses <Link>
const renderOverviewTab = (props: {
  alert: Alert;
  taskRuns: TaskRun[];
  onNavigateToTab: (tab: 'findings' | 'raw' | 'analysis', subtab?: string) => void;
}) =>
  render(
    <MemoryRouter>
      <OverviewTab {...props} />
    </MemoryRouter>
  );

// Mock backendApi
const mockGetArtifacts = vi.fn();
vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    getArtifacts: (...args: unknown[]) => mockGetArtifacts(...args),
  },
}));

// Mock useErrorHandler
vi.mock('../../../hooks/useErrorHandler', () => ({
  default: () => ({
    error: null,
    handleError: vi.fn(),
    createContext: vi.fn(),
    runSafe: vi.fn(async (promise: Promise<unknown>) => {
      try {
        const r = await promise;
        return [r, null];
      } catch (e) {
        return [null, e];
      }
    }),
  }),
}));

// Constants
const ALERT_ID = 'alert-001';
const ANALYSIS_ID = 'analysis-001';
const EVENT_TRIGGERED_TEXT = 'Event Triggered';
const ALERT_INGESTED_TEXT = 'Alert Ingested';
const TEST_TIMESTAMP = '2025-01-15T10:00:00Z';

// Factory helpers
const makeAlert = (overrides: Partial<Alert> = {}): Alert =>
  ({
    alert_id: ALERT_ID,
    human_readable_id: 'ALT-001',
    title: 'Test Alert',
    severity: 'high',
    triggering_event_time: TEST_TIMESTAMP,
    created_at: '2025-01-15T10:01:00Z',
    updated_at: '2025-01-15T10:02:00Z',
    ingested_at: '2025-01-15T10:01:00Z',
    analysis_status: 'completed',
    raw_alert: '{}',
    tenant_id: 'test-tenant',
    content_hash: 'hash-001',
    ...overrides,
  }) as Alert;

const makeTaskRun = (overrides: Partial<TaskRun> = {}): TaskRun => ({
  id: 'run-001',
  tenant_id: 'tenant-1',
  task_id: 'task-001',
  task_name: 'Test Task',
  status: 'completed',
  duration: 'PT2S',
  started_at: TEST_TIMESTAMP,
  input_type: 'inline',
  input_location: '{}',
  input_content_type: 'application/json',
  created_at: TEST_TIMESTAMP,
  updated_at: '2025-01-15T10:00:02Z',
  ...overrides,
});

const makeArtifact = (overrides: Partial<Artifact> = {}): Artifact => ({
  id: 'artifact-001',
  tenant_id: 'tenant-1',
  name: 'test-artifact.json',
  artifact_type: 'report',
  mime_type: 'application/json',
  tags: [],
  size_bytes: 1024,
  sha256: 'abc123',
  md5: null,
  storage_class: 'inline',
  content: '{"key": "value"}',
  download_url: null,
  bucket: null,
  object_key: null,
  alert_id: ALERT_ID,
  task_run_id: null,
  workflow_run_id: null,
  workflow_node_instance_id: null,
  analysis_id: ANALYSIS_ID,
  integration_id: null,
  source: 'auto_capture',
  created_at: '2025-01-15T10:05:00Z',
  ...overrides,
});

describe('OverviewTab', () => {
  const mockOnNavigateToTab = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetArtifacts.mockResolvedValue({ artifacts: [] });
  });

  it('renders without crashing with minimal alert data', () => {
    renderOverviewTab({ alert: makeAlert(), taskRuns: [], onNavigateToTab: mockOnNavigateToTab });

    // Timeline is inside the collapsed "Investigation Details" section
    // Open it first by clicking the summary
    const details = screen.getByText('Investigation Details');
    details.click();

    expect(screen.getByText(EVENT_TRIGGERED_TEXT)).toBeInTheDocument();
    expect(screen.getByText(ALERT_INGESTED_TEXT)).toBeInTheDocument();
    expect(screen.getByText('Artifacts')).toBeInTheDocument();
  });

  it('shows analysis status in timeline when analysis has started', () => {
    const alert = makeAlert({
      current_analysis: {
        id: ANALYSIS_ID,
        alert_id: ALERT_ID,
        tenant_id: 'tenant-1',
        status: 'completed',
        started_at: '2025-01-15T10:02:00Z',
        completed_at: '2025-01-15T10:04:00Z',
        steps_progress: {},
        created_at: '2025-01-15T10:02:00Z',
        updated_at: '2025-01-15T10:04:00Z',
      },
    });

    renderOverviewTab({ alert: alert, taskRuns: [], onNavigateToTab: mockOnNavigateToTab });

    // Open Investigation Details
    screen.getByText('Investigation Details').click();

    expect(screen.getByText('Analysis Started')).toBeInTheDocument();
    expect(screen.getByText('Analysis Completed')).toBeInTheDocument();
  });

  it('displays timing information with analysis duration', () => {
    const alert = makeAlert({
      current_analysis_id: ANALYSIS_ID,
      current_analysis: {
        id: ANALYSIS_ID,
        alert_id: ALERT_ID,
        tenant_id: 'tenant-1',
        status: 'completed',
        started_at: TEST_TIMESTAMP,
        completed_at: '2025-01-15T10:02:30Z',
        steps_progress: {},
        created_at: TEST_TIMESTAMP,
        updated_at: '2025-01-15T10:02:30Z',
      },
    });

    renderOverviewTab({ alert: alert, taskRuns: [], onNavigateToTab: mockOnNavigateToTab });

    // Open Investigation Details
    screen.getByText('Investigation Details').click();

    expect(screen.getByText('Analysis Time')).toBeInTheDocument();
    expect(screen.getByText('2m 30s')).toBeInTheDocument();
  });

  it('shows artifact count after fetching', async () => {
    const artifacts = [makeArtifact(), makeArtifact({ id: 'artifact-002', name: 'second.json' })];
    mockGetArtifacts.mockResolvedValue({ artifacts });

    const alert = makeAlert({ current_analysis_id: ANALYSIS_ID });

    renderOverviewTab({ alert: alert, taskRuns: [], onNavigateToTab: mockOnNavigateToTab });

    // Open Investigation Details to see artifact count
    screen.getByText('Investigation Details').click();

    await waitFor(() => {
      expect(screen.getByText('2')).toBeInTheDocument();
    });
  });

  it('calls onNavigateToTab when stat card with onClick is clicked', async () => {
    const user = userEvent.setup();
    const taskRuns = [
      makeTaskRun({ status: 'completed' }),
      makeTaskRun({ id: 'run-002', status: 'failed' }),
    ];

    renderOverviewTab({
      alert: makeAlert(),
      taskRuns: taskRuns,
      onNavigateToTab: mockOnNavigateToTab,
    });

    // Open Investigation Details
    screen.getByText('Investigation Details').click();

    // Click the Findings stat card
    const findingsCard = screen.getByText('Findings').closest('button');
    expect(findingsCard).toBeInTheDocument();
    await user.click(findingsCard!);

    expect(mockOnNavigateToTab).toHaveBeenCalledWith('findings');
  });

  it('shows key entities when risk entity data is present', () => {
    const alert = makeAlert({
      device: { hostname: 'server-01.example.com' },
    });

    renderOverviewTab({ alert: alert, taskRuns: [], onNavigateToTab: mockOnNavigateToTab });

    expect(screen.getByText('Primary Risk Entity')).toBeInTheDocument();
    expect(screen.getByText('server-01.example.com')).toBeInTheDocument();
  });

  it('renders primary IOC value as a clickable link', () => {
    const alert = makeAlert({
      observables: [{ type_id: 6, type: 'domain', value: 'malware.example.com' }],
    });

    renderOverviewTab({ alert: alert, taskRuns: [], onNavigateToTab: mockOnNavigateToTab });

    // Value is rendered in both the Primary IOC card and the observables table
    const links = screen.getAllByText('malware.example.com');
    expect(links.length).toBeGreaterThanOrEqual(1);
    expect(links[0].tagName).toBe('A');
    expect(links[0]).toHaveAttribute(
      'href',
      `/alerts?search=${encodeURIComponent('malware.example.com')}`
    );
  });

  it('renders observables table when multiple observables are present', () => {
    const alert = makeAlert({
      observables: [
        { type_id: 6, type: 'domain', value: 'c2.bad-actor.net' },
        { type_id: 6, type: 'domain', value: 'evil.example.com' },
      ],
    });

    renderOverviewTab({ alert: alert, taskRuns: [], onNavigateToTab: mockOnNavigateToTab });

    expect(screen.getByText('Observables (2)')).toBeInTheDocument();

    // The first observable appears twice (Primary IOC card + table row)
    const c2Links = screen.getAllByText('c2.bad-actor.net');
    expect(c2Links[0].tagName).toBe('A');
    expect(c2Links[0]).toHaveAttribute('href', '/alerts?search=c2.bad-actor.net');

    const domainLink = screen.getByText('evil.example.com');
    expect(domainLink.tagName).toBe('A');

    // First observable gets the primary badge in the table
    expect(screen.getByText('primary')).toBeInTheDocument();
  });
});
