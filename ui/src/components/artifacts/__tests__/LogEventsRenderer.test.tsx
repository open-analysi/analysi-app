import { render } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

import { DataUnavailableMessage } from '../LogEventsRenderer';

// Mock JsonRenderer since we don't need to test its functionality
vi.mock('../JsonRenderer', () => ({
  default: ({ title }: { title: string }) => <div data-testid="json-renderer">{title}</div>,
}));

describe('LogEventsRenderer', () => {
  it('renders the DataUnavailableMessage component when data is unavailable', () => {
    const { container } = render(<DataUnavailableMessage category="timeline" />);

    expect(container.textContent).toContain('Triggering Events');
    expect(container.textContent).toContain('Data Unavailable');
    expect(container.textContent).toContain('Failed to load data for Triggering Events');
  });

  it('shows different message for Supporting Events', () => {
    const { container } = render(<DataUnavailableMessage category="logs" />);

    expect(container.textContent).toContain('Supporting Events');
    expect(container.textContent).toContain('Failed to load data for Supporting Events');
  });
});
