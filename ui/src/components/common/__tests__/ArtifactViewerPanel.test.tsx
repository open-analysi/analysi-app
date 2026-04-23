import React from 'react';

import { render, screen, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import type { Artifact } from '../../../types/artifact';
import { ArtifactViewerPanel } from '../ArtifactViewerPanel';

// Fully mock HeadlessUI to avoid transition/focus-trap timing issues in jsdom
vi.mock('@headlessui/react', () => {
  function MockDialog({
    children,
  }: Readonly<{
    children: React.ReactNode;
    onClose: () => void;
    open?: boolean;
    className?: string;
  }>) {
    return <div role="dialog">{children}</div>;
  }
  function MockDialogPanel({
    children,
    className,
  }: Readonly<{
    children: React.ReactNode;
    className?: string;
  }>) {
    return (
      <div data-testid="dialog-panel" className={className}>
        {children}
      </div>
    );
  }
  function MockDialogTitle({
    children,
    className,
  }: Readonly<{
    children: React.ReactNode;
    className?: string;
  }>) {
    return <h2 className={className}>{children}</h2>;
  }
  function MockDialogDescription({ children }: Readonly<{ children: React.ReactNode }>) {
    return <p>{children}</p>;
  }

  MockDialog.Panel = MockDialogPanel;
  MockDialog.Title = MockDialogTitle;
  MockDialog.Description = MockDialogDescription;

  function MockTransition({ children }: Readonly<{ children: React.ReactNode; show?: boolean }>) {
    return <>{children}</>;
  }
  function MockTransitionChild({ children }: Readonly<{ children: React.ReactNode }>) {
    return <>{children}</>;
  }
  MockTransition.Child = MockTransitionChild;

  return {
    Dialog: MockDialog,
    DialogPanel: MockDialogPanel,
    DialogTitle: MockDialogTitle,
    Transition: Object.assign(MockTransition, { Child: MockTransitionChild }),
    TransitionChild: MockTransitionChild,
  };
});

// Mock backendApi
const mockGetArtifact = vi.fn();
vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    getArtifact: (...args: unknown[]) => mockGetArtifact(...args),
  },
}));

// Mock timezone store
vi.mock('../../../store/timezoneStore', () => ({
  useTimezoneStore: () => ({ timezone: 'UTC' }),
}));

// Stable runSafe function to avoid infinite useEffect re-triggers
const stableRunSafe = vi.fn(async (promise: Promise<unknown>) => {
  try {
    const r = await promise;
    return [r, null];
  } catch (e) {
    return [null, e];
  }
});

// Mock useErrorHandler with a stable runSafe reference
vi.mock('../../../hooks/useErrorHandler', () => ({
  default: () => ({
    error: null,
    handleError: vi.fn(),
    createContext: vi.fn(),
    runSafe: stableRunSafe,
  }),
}));

// Constants
const ARTIFACT_NAME = 'test-report.json';
const LOADING_TEXT = 'Loading content...';
const COPY_BUTTON_TITLE = 'Copy to clipboard';

// Factory helper
const makeArtifact = (overrides: Partial<Artifact> = {}): Artifact => ({
  id: 'artifact-001',
  tenant_id: 'tenant-1',
  name: ARTIFACT_NAME,
  artifact_type: 'report',
  mime_type: 'application/json',
  tags: [],
  size_bytes: 256,
  sha256: 'abc123def456',
  md5: null,
  storage_class: 'inline',
  content: null,
  download_url: null,
  bucket: null,
  object_key: null,
  alert_id: 'alert-001',
  task_run_id: null,
  workflow_run_id: null,
  workflow_node_instance_id: null,
  analysis_id: 'analysis-001',
  integration_id: null,
  source: 'auto_capture',
  created_at: '2025-01-15T10:00:00Z',
  ...overrides,
});

// Async render helper
async function renderPanel(artifact: Artifact, onClose = vi.fn()) {
  const result = render(<ArtifactViewerPanel artifact={artifact} onClose={onClose} />);
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
  return result;
}

describe('ArtifactViewerPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // By default the API returns the artifact with no content
    mockGetArtifact.mockResolvedValue(makeArtifact({ content: null }));
  });

  it('renders the dialog with artifact name', async () => {
    await renderPanel(makeArtifact());

    expect(screen.getByText(ARTIFACT_NAME)).toBeInTheDocument();
  });

  it('shows loading state while fetching content', async () => {
    // Make the API call hang indefinitely
    mockGetArtifact.mockReturnValue(new Promise(() => {}));

    await renderPanel(makeArtifact());

    expect(screen.getByText(LOADING_TEXT)).toBeInTheDocument();
  });

  it('renders JSON content formatted when mime_type is application/json', async () => {
    const jsonContent = { findings: [{ severity: 'high', description: 'Test finding' }] };
    mockGetArtifact.mockResolvedValue(
      makeArtifact({
        content: JSON.stringify(jsonContent),
        mime_type: 'application/json',
      })
    );

    await renderPanel(makeArtifact({ mime_type: 'application/json' }));

    // Wait for content to load after the fetch resolves
    await waitFor(() => {
      expect(screen.getByText(/"findings"/)).toBeInTheDocument();
    });
  });

  it('shows copy button', async () => {
    await renderPanel(makeArtifact());

    expect(screen.getByTitle(COPY_BUTTON_TITLE)).toBeInTheDocument();
  });
});
