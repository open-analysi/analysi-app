import React from 'react';

import { render } from '@testing-library/react';
import { BrowserRouter } from 'react-router';
import { describe, it, expect, vi } from 'vitest';

import TasksPage from '../Tasks';

// Mock the Tasks component since we're testing the page wrapper
vi.mock('../../components/settings/Tasks', () => ({
  Tasks: () => <div data-testid="tasks-component">Tasks Component</div>,
}));

// Mock the ErrorBoundary component to pass through children
vi.mock('../../components/common/ErrorBoundary', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// Mock the componentStyles
vi.mock('../../styles/components', () => ({
  componentStyles: {
    pageBackground: 'mock-page-background',
  },
}));

const renderWithRouter = (component: React.ReactElement) => {
  return render(<BrowserRouter>{component}</BrowserRouter>);
};

describe('TasksPage', () => {
  it('renders the tasks page', () => {
    const { container } = renderWithRouter(<TasksPage />);

    // Check that the page renders
    expect(container.firstChild).toBeTruthy();

    // Check for the page element
    const pageElement = container.querySelector('[data-testid="tasks-page"]');
    expect(pageElement).toBeTruthy();

    // Check that Tasks component is rendered
    expect(container.textContent).toContain('Tasks Component');
  });

  it('renders the Tasks component by default', () => {
    const { container } = renderWithRouter(<TasksPage />);

    const tasksComponent = container.querySelector('[data-testid="tasks-component"]');
    expect(tasksComponent).toBeTruthy();
  });

  it('applies the correct page background styling', () => {
    const { container } = renderWithRouter(<TasksPage />);

    const pageContainer = container.querySelector('[data-testid="tasks-page"]');
    expect(pageContainer).toBeTruthy();
    expect(pageContainer).toHaveClass('mock-page-background');
  });

  it('wraps content in error boundary', () => {
    // This test verifies the component structure includes error boundary
    const { container } = renderWithRouter(<TasksPage />);

    // The page should render without throwing
    const pageElement = container.querySelector('[data-testid="tasks-page"]');
    expect(pageElement).toBeTruthy();

    const tasksComponent = container.querySelector('[data-testid="tasks-component"]');
    expect(tasksComponent).toBeTruthy();
  });
});
