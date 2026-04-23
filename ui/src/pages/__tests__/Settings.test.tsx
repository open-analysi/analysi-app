import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router';
import { describe, it, expect, vi } from 'vitest';

import Settings from '../Settings';

vi.mock('../../components/settings/AnalysisGroups', () => ({
  AnalysisGroups: () => <div data-testid="analysis-groups">Analysis Groups</div>,
}));

vi.mock('../../components/settings/AlertRoutingRules', () => ({
  AlertRoutingRules: () => <div data-testid="alert-routing-rules">Alert Routing Rules</div>,
}));

vi.mock('../../components/settings/ControlEventSection', () => ({
  ControlEventSection: () => <div data-testid="control-event-section">Control Events</div>,
}));

const renderSettings = (search = '') => {
  window.history.pushState({}, '', `/settings${search}`);
  return render(
    <BrowserRouter>
      <Settings />
    </BrowserRouter>
  );
};

describe('Settings', () => {
  it('renders the settings landing page with section cards', () => {
    const { container } = renderSettings();

    expect(container.firstChild).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
    expect(screen.getByText('Analysis Groups')).toBeInTheDocument();
    expect(screen.getByText('Alert Routing Rules')).toBeInTheDocument();
    expect(screen.getByText('Event Reaction Rules')).toBeInTheDocument();
  });

  it('renders Analysis Groups section when section param is set', () => {
    renderSettings('?section=analysis-groups');

    expect(screen.getByTestId('analysis-groups')).toBeInTheDocument();
  });
});
