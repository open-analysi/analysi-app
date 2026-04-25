import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { AccountSettings } from '../AccountSettings';

// Mock the timezone store
vi.mock('../../store/timezoneStore', () => ({
  useTimezoneStore: vi.fn(() => ({
    timezone: 'America/Los_Angeles',
    setTimezone: vi.fn(),
  })),
}));

// Mock the auth store
vi.mock('../../store/authStore', () => ({
  useAuthStore: vi.fn(() => ({
    email: 'test@analysi.local',
    name: 'Test User',
    tenant_id: 'default',
    roles: ['owner'],
    isAuthenticated: true,
  })),
}));

// Mock moment-timezone
vi.mock('moment-timezone', () => {
  const mockMoment: any = () => ({
    tz: (_timezone: string) => ({
      format: (format: string) => {
        if (format === 'Z') return '-08:00';
        return 'Thursday, December 5, 2024 10:00 AM';
      },
    }),
  });

  // Mock moment.tz() function
  mockMoment.tz = (_timezone: string) => ({
    format: (format: string) => {
      if (format === 'Z') return '-08:00';
      return 'Thursday, December 5, 2024 10:00 AM';
    },
  });

  // Mock moment.tz.names() function
  mockMoment.tz.names = () => ['America/Los_Angeles', 'America/New_York', 'Europe/London'];

  return { default: mockMoment };
});

describe('AccountSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the page heading', () => {
    render(<AccountSettings />);

    expect(
      screen.getByRole('heading', { name: /Account Settings/i, level: 1 })
    ).toBeInTheDocument();
  });

  it('renders the page description', () => {
    render(<AccountSettings />);

    expect(screen.getByText(/Manage your account preferences and settings/i)).toBeInTheDocument();
  });

  it('renders the Profile section with user data from authStore', () => {
    render(<AccountSettings />);

    expect(screen.getByRole('heading', { name: /Profile/i, level: 2 })).toBeInTheDocument();
    expect(screen.getByText('Test User')).toBeInTheDocument();
    expect(screen.getByText('test@analysi.local')).toBeInTheDocument();
    expect(screen.getByText('default')).toBeInTheDocument();
    expect(screen.getByText('owner')).toBeInTheDocument();
  });

  it('renders the Preferences section with timezone selector', () => {
    render(<AccountSettings />);

    expect(screen.getByRole('heading', { name: /Preferences/i, level: 2 })).toBeInTheDocument();
    expect(screen.getByLabelText(/Timezone/i)).toBeInTheDocument();
  });

  it('renders the Notifications section', () => {
    render(<AccountSettings />);

    expect(screen.getByRole('heading', { name: /Notifications/i, level: 2 })).toBeInTheDocument();
    expect(screen.getByText(/Notification settings coming soon/i)).toBeInTheDocument();
  });

  it('renders timezone dropdown with current timezone', () => {
    render(<AccountSettings />);

    const select = screen.getByLabelText(/Timezone/i);
    expect(select).toBeInTheDocument();
    expect(select).toHaveValue('America/Los_Angeles');
  });

  it('renders current time display', () => {
    render(<AccountSettings />);

    expect(screen.getByText(/Current time:/i)).toBeInTheDocument();
  });
});
