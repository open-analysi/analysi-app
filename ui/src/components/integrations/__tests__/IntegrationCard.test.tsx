import { render, screen, fireEvent, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { Integration, IntegrationStatus } from '../../../types/integration';
import { IntegrationCard } from '../IntegrationCard';

const mockNavigate = vi.fn();

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return { ...actual, useNavigate: () => mockNavigate };
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

const makeIntegration = (overrides: Partial<Integration> = {}): Integration => ({
  id: 'splunk-1',
  name: 'Splunk SIEM',
  type: 'splunk',
  status: IntegrationStatus.Connected,
  description: 'Primary Splunk instance',
  ...overrides,
});

const renderCard = (integration = makeIntegration()) => {
  const result = render(
    <MemoryRouter>
      <IntegrationCard integration={integration} />
    </MemoryRouter>
  );
  // The outer card div has role="button" and tabIndex=0
  const cardEl = screen.getByRole('button', { name: /splunk siem/i });
  return { ...result, cardEl };
};

describe('IntegrationCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders integration name and status', () => {
    renderCard();
    expect(screen.getByText('Splunk SIEM')).toBeInTheDocument();
    expect(screen.getByText(IntegrationStatus.Connected)).toBeInTheDocument();
  });

  it('renders description when provided', () => {
    renderCard();
    expect(screen.getByText('Primary Splunk instance')).toBeInTheDocument();
  });

  it('does not render description when absent', () => {
    render(
      <MemoryRouter>
        <IntegrationCard integration={makeIntegration({ description: undefined })} />
      </MemoryRouter>
    );
    expect(screen.queryByText('Primary Splunk instance')).not.toBeInTheDocument();
  });

  it('applies green color for connected status', () => {
    renderCard();
    const statusEl = screen.getByText(IntegrationStatus.Connected);
    expect(statusEl.className).toContain('text-green-500');
  });

  it('applies red color for disconnected status', () => {
    render(
      <MemoryRouter>
        <IntegrationCard
          integration={makeIntegration({ status: IntegrationStatus.NotConnected })}
        />
      </MemoryRouter>
    );
    const statusEl = screen.getByText(IntegrationStatus.NotConnected);
    expect(statusEl.className).toContain('text-red-500');
  });

  it('navigates to integration detail on card click', () => {
    const { cardEl } = renderCard();
    fireEvent.click(cardEl);
    expect(mockNavigate).toHaveBeenCalledWith('/integrations/splunk-1');
  });

  it('navigates on Enter key press', () => {
    const { cardEl } = renderCard();
    fireEvent.keyDown(cardEl, { key: 'Enter' });
    expect(mockNavigate).toHaveBeenCalledWith('/integrations/splunk-1');
  });

  it('navigates on Space key press', () => {
    const { cardEl } = renderCard();
    fireEvent.keyDown(cardEl, { key: ' ' });
    expect(mockNavigate).toHaveBeenCalledWith('/integrations/splunk-1');
  });

  it('does not navigate on other key presses', () => {
    const { cardEl } = renderCard();
    fireEvent.keyDown(cardEl, { key: 'Tab' });
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('shows Configure and Test Connection buttons', () => {
    renderCard();
    expect(screen.getByText('Configure')).toBeInTheDocument();
    expect(screen.getByText('Test Connection')).toBeInTheDocument();
  });

  it('Configure button triggers configuring state and resolves', async () => {
    renderCard();

    // Click Configure — starts async handleConfigure which sets isConfiguring=true
    act(() => {
      fireEvent.click(screen.getByText('Configure'));
    });

    // State is now isConfiguring=true, button text changed
    expect(screen.getByText('Configuring...')).toBeInTheDocument();

    // Advance the 1s timer and flush microtasks so the async promise chain resolves
    await act(async () => {
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
    });

    // handleConfigure completes: setIsConfiguring(false)
    expect(screen.getByText('Configure')).toBeInTheDocument();
  });

  it('Test Connection click does not navigate (stopPropagation)', () => {
    renderCard();
    fireEvent.click(screen.getByText('Test Connection'));
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('disables buttons while configuring', () => {
    renderCard();

    act(() => {
      fireEvent.click(screen.getByText('Configure'));
    });

    expect(screen.getByText('Configuring...')).toBeDisabled();
    expect(screen.getByText('Testing...')).toBeDisabled();

    act(() => {
      vi.advanceTimersByTime(1000);
    });
  });

  it('does not navigate while configuring', () => {
    const { cardEl } = renderCard();

    // Use Test Connection to enter configuring state (it has stopPropagation so
    // the click won't bubble to the card and trigger navigate)
    act(() => {
      fireEvent.click(screen.getByText('Test Connection'));
    });

    expect(screen.getByText('Testing...')).toBeInTheDocument();
    mockNavigate.mockClear();

    // Click the card while isConfiguring=true — onClick guards with `if (!isConfiguring)`
    fireEvent.click(cardEl);
    expect(mockNavigate).not.toHaveBeenCalled();

    // Clean up the 2s testConnection timer
    act(() => {
      vi.advanceTimersByTime(2000);
    });
  });
});
