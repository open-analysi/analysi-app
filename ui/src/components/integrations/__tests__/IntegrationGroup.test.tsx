import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, it, expect, vi } from 'vitest';

import {
  IntegrationGroup as IIntegrationGroup,
  IntegrationStatus,
} from '../../../types/integration';
import { IntegrationGroup } from '../IntegrationGroup';

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return { ...actual, useNavigate: () => vi.fn() };
});

vi.mock('../../../hooks/useErrorHandler', () => ({
  default: () => ({
    error: { hasError: false, message: '' },
    clearError: vi.fn(),
    handleError: vi.fn(),
    createContext: vi.fn(),
    runSafe: vi
      .fn()
      .mockImplementation(async (promise: Promise<unknown>) => [await promise, undefined]),
  }),
}));

const makeGroup = (overrides: Partial<IIntegrationGroup> = {}): IIntegrationGroup => ({
  type: 'SIEM',
  description: 'Security Information and Event Management',
  integrations: [
    {
      id: 'splunk-1',
      name: 'Splunk',
      type: 'splunk',
      status: IntegrationStatus.Connected,
    },
    {
      id: 'elastic-1',
      name: 'Elastic SIEM',
      type: 'elastic',
      status: IntegrationStatus.NotConnected,
      description: 'Elastic instance',
    },
  ],
  ...overrides,
});

const renderGroup = (group = makeGroup()) =>
  render(
    <MemoryRouter>
      <IntegrationGroup group={group} />
    </MemoryRouter>
  );

describe('IntegrationGroup', () => {
  it('renders group type as heading', () => {
    renderGroup();
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('SIEM');
  });

  it('renders group description', () => {
    renderGroup();
    expect(screen.getByText('Security Information and Event Management')).toBeInTheDocument();
  });

  it('does not render description when absent', () => {
    renderGroup(makeGroup({ description: '' }));
    expect(screen.queryByText('Security Information and Event Management')).not.toBeInTheDocument();
  });

  it('renders an IntegrationCard for each integration', () => {
    renderGroup();
    expect(screen.getByText('Splunk')).toBeInTheDocument();
    expect(screen.getByText('Elastic SIEM')).toBeInTheDocument();
  });

  it('renders empty group without error', () => {
    renderGroup(makeGroup({ integrations: [] }));
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('SIEM');
    expect(screen.queryByText('Configure')).not.toBeInTheDocument();
  });
});
