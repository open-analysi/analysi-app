import React from 'react';

import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router';
import { describe, it, expect, vi } from 'vitest';

import { RootLayout } from '../RootLayout';

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

// Helper to render with router (RootLayout uses Outlet which requires router context)
const renderWithRouter = (component: React.ReactElement) => {
  return render(<BrowserRouter>{component}</BrowserRouter>);
};

describe('RootLayout', () => {
  it('renders the Sidebar', () => {
    renderWithRouter(<RootLayout />);

    // Check if sidebar logo is present (indicating sidebar is rendered)
    const logo = screen.getByAltText(/Analysi/i);
    expect(logo).toBeInTheDocument();
  });

  it('renders the main content area', () => {
    const { container } = renderWithRouter(<RootLayout />);

    // Check if main element exists
    const main = container.querySelector('main');
    expect(main).toBeInTheDocument();
  });

  it('does not render TopNav component', () => {
    const { container } = renderWithRouter(<RootLayout />);

    // TopNav had a specific height and class, verify they're not present
    const topNavBar = container.querySelector('.h-16.bg-dark-800');
    expect(topNavBar).not.toBeInTheDocument();
  });

  it('does not render settings button from TopNav', () => {
    renderWithRouter(<RootLayout />);

    // Old TopNav had a settings button with title="Account settings"
    const settingsButton = screen.queryByTitle('Account settings');
    expect(settingsButton).not.toBeInTheDocument();
  });

  it('does not render user profile icon from TopNav', () => {
    renderWithRouter(<RootLayout />);

    // Old TopNav had a user icon with title="User profile"
    const userIcon = screen.queryByTitle('User profile');
    expect(userIcon).not.toBeInTheDocument();
  });

  it('has proper layout structure (sidebar + main)', () => {
    const { container } = renderWithRouter(<RootLayout />);

    // Check for flex container
    const flexContainer = container.querySelector('.flex.min-h-screen');
    expect(flexContainer).toBeInTheDocument();

    // Sidebar should be present (as aside element)
    const sidebar = container.querySelector('aside[aria-label="Main navigation"]');
    expect(sidebar).toBeInTheDocument();

    // Main content area should be present
    const main = container.querySelector('main');
    expect(main).toBeInTheDocument();
  });
});
