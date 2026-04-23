import React from 'react';

import { fireEvent, render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router';
import { describe, it, expect, beforeEach, vi } from 'vitest';

import { Sidebar } from '../sidebar';

const COLLAPSE_LABEL = 'Collapse sidebar';

// Helper to render with router
const renderWithRouter = (component: React.ReactElement) => {
  return render(<BrowserRouter>{component}</BrowserRouter>);
};

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    clear: () => {
      store = {};
    },
  };
})();

Object.defineProperty(window, 'localStorage', { value: localStorageMock });

beforeEach(() => {
  localStorageMock.clear();
});

describe('Sidebar', () => {
  it('renders the logo', () => {
    renderWithRouter(<Sidebar />);
    const logo = screen.getByAltText(/Analysi/i);
    expect(logo).toBeInTheDocument();
  });

  it('renders all navigation items in expanded mode', () => {
    renderWithRouter(<Sidebar />);

    // Core navigation items
    expect(screen.getByText('Alerts')).toBeInTheDocument();
    expect(screen.getByText('Integrations')).toBeInTheDocument();
    expect(screen.getByText('Tasks')).toBeInTheDocument();
    expect(screen.getByText('Workflows')).toBeInTheDocument();
    expect(screen.getByText('Workbench')).toBeInTheDocument();
    expect(screen.getByText('History')).toBeInTheDocument();
    expect(screen.getByText('List')).toBeInTheDocument();
    expect(screen.getByText('Skills')).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
    expect(screen.getByText('Audit Trail')).toBeInTheDocument();
    expect(screen.getByText('Account')).toBeInTheDocument();
  });

  it('renders the Account navigation item', () => {
    renderWithRouter(<Sidebar />);
    const accountLink = screen.getByText('Account');
    expect(accountLink).toBeInTheDocument();
  });

  it('Account button opens popover with link to /account-settings', () => {
    renderWithRouter(<Sidebar />);
    const accountButton = screen.getByText('Account').closest('button');
    expect(accountButton).toBeInTheDocument();
    fireEvent.click(accountButton!);
    const profileLink = screen.getByRole('menuitem', { name: /Profile/i });
    expect(profileLink).toHaveAttribute('href', '/account-settings');
  });

  it('renders navigation items as links', () => {
    renderWithRouter(<Sidebar />);
    const alertsLink = screen.getByText('Alerts').closest('a');
    expect(alertsLink).toBeInTheDocument();
    expect(alertsLink).toHaveAttribute('href');
  });

  it('renders Graph navigation item', () => {
    renderWithRouter(<Sidebar />);
    const graph = screen.getByText('Graph');
    expect(graph).toBeInTheDocument();
  });

  it('renders section headers in expanded mode', () => {
    renderWithRouter(<Sidebar />);
    expect(screen.getByText('Core')).toBeInTheDocument();
    expect(screen.getByText('Develop')).toBeInTheDocument();
    expect(screen.getByText('Knowledge')).toBeInTheDocument();
  });

  it('renders collapse toggle button', () => {
    renderWithRouter(<Sidebar />);
    const toggleBtn = screen.getByLabelText(COLLAPSE_LABEL);
    expect(toggleBtn).toBeInTheDocument();
  });

  it('toggles between collapsed and expanded state', () => {
    renderWithRouter(<Sidebar />);

    // Initially expanded — labels should be visible
    expect(screen.getByText('Alerts')).toBeInTheDocument();

    // Click collapse
    const collapseBtn = screen.getByLabelText(COLLAPSE_LABEL);
    fireEvent.click(collapseBtn);

    // After collapse — expand button should appear, labels hidden
    expect(screen.getByLabelText('Expand sidebar')).toBeInTheDocument();
    expect(screen.queryByText('Alerts')).not.toBeInTheDocument();
  });

  it('persists collapsed state to localStorage', () => {
    renderWithRouter(<Sidebar />);

    const collapseBtn = screen.getByLabelText(COLLAPSE_LABEL);
    fireEvent.click(collapseBtn);

    expect(localStorageMock.setItem).toHaveBeenCalledWith('sidebar-collapsed', 'true');
  });

  it('renders admin items at the bottom', () => {
    renderWithRouter(<Sidebar />);
    expect(screen.getByText('Settings')).toBeInTheDocument();
    expect(screen.getByText('Audit Trail')).toBeInTheDocument();
    expect(screen.getByText('Account')).toBeInTheDocument();
  });

  it('has proper sidebar ARIA label', () => {
    const { container } = renderWithRouter(<Sidebar />);
    const aside = container.querySelector('aside[aria-label="Main navigation"]');
    expect(aside).toBeInTheDocument();
  });

  describe('submenu flyouts', () => {
    it('opens Workbench flyout on click', () => {
      renderWithRouter(<Sidebar />);

      const workbenchLink = screen.getByText('Workbench').closest('a')!;
      fireEvent.click(workbenchLink);

      // Flyout should show submenu items
      expect(screen.getByRole('menu')).toBeInTheDocument();
      expect(screen.getByRole('menuitem', { name: /Tasks/ })).toBeInTheDocument();
      expect(screen.getByRole('menuitem', { name: /Workflows/ })).toBeInTheDocument();
    });

    it('opens History flyout on click', () => {
      renderWithRouter(<Sidebar />);

      const historyLink = screen.getByText('History').closest('a')!;
      fireEvent.click(historyLink);

      expect(screen.getByRole('menu')).toBeInTheDocument();
      expect(screen.getByRole('menuitem', { name: /Task Runs/ })).toBeInTheDocument();
      expect(screen.getByRole('menuitem', { name: /Workflow Runs/ })).toBeInTheDocument();
      expect(screen.getByRole('menuitem', { name: /Task Building/ })).toBeInTheDocument();
    });

    it('closes flyout on Escape key', () => {
      renderWithRouter(<Sidebar />);

      // Open the flyout
      const workbenchLink = screen.getByText('Workbench').closest('a')!;
      fireEvent.click(workbenchLink);
      expect(screen.getByRole('menu')).toBeInTheDocument();

      // Press Escape
      fireEvent.keyDown(document, { key: 'Escape' });

      // Flyout should be closed
      expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    });

    it('toggles flyout open and closed on repeated clicks', () => {
      renderWithRouter(<Sidebar />);

      const workbenchLink = screen.getByText('Workbench').closest('a')!;

      // Open
      fireEvent.click(workbenchLink);
      expect(screen.getByRole('menu')).toBeInTheDocument();

      // Close
      fireEvent.click(workbenchLink);
      expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    });

    it('sets aria-expanded on submenu trigger', () => {
      renderWithRouter(<Sidebar />);

      const workbenchLink = screen.getByText('Workbench').closest('a')!;
      expect(workbenchLink).toHaveAttribute('aria-expanded', 'false');

      fireEvent.click(workbenchLink);
      expect(workbenchLink).toHaveAttribute('aria-expanded', 'true');
    });

    it('sets aria-haspopup on submenu triggers', () => {
      renderWithRouter(<Sidebar />);

      const workbenchLink = screen.getByText('Workbench').closest('a')!;
      expect(workbenchLink).toHaveAttribute('aria-haspopup', 'true');

      const historyLink = screen.getByText('History').closest('a')!;
      expect(historyLink).toHaveAttribute('aria-haspopup', 'true');
    });
  });

  describe('collapsed mode', () => {
    it('hides section headers when collapsed', () => {
      renderWithRouter(<Sidebar />);

      // Collapse
      fireEvent.click(screen.getByLabelText(COLLAPSE_LABEL));

      // Section headers should not be visible
      expect(screen.queryByText('Core')).not.toBeInTheDocument();
      expect(screen.queryByText('Develop')).not.toBeInTheDocument();
      expect(screen.queryByText('Knowledge')).not.toBeInTheDocument();
    });

    it('shows section separators when collapsed', () => {
      const { container } = renderWithRouter(<Sidebar />);

      fireEvent.click(screen.getByLabelText(COLLAPSE_LABEL));

      // There should be separator divs between sections (sections 2 and 3 get separators)
      const separators = container.querySelectorAll('.border-t.border-dark-600');
      // 2 section separators + 1 admin separator = at least 3
      expect(separators.length).toBeGreaterThanOrEqual(3);
    });
  });
});
