import React from 'react';

import { UserCircleIcon } from '@heroicons/react/24/outline';
import moment from 'moment-timezone';

import { useAuthStore } from '../store/authStore';
import { useTimezoneStore } from '../store/timezoneStore';

export const AccountSettings: React.FC = () => {
  const { timezone, setTimezone } = useTimezoneStore();
  const { email, name, tenant_id, roles } = useAuthStore();
  const timezones = moment.tz.names();

  return (
    <div className="h-full overflow-auto bg-dark-900">
      <div className="max-w-4xl mx-auto p-6">
        {/* Page Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <UserCircleIcon className="w-8 h-8 text-primary" />
            <h1 className="text-2xl font-semibold text-gray-100">Account Settings</h1>
          </div>
          <p className="text-sm text-gray-400">Manage your account preferences and settings</p>
        </div>

        {/* Settings Sections */}
        <div className="space-y-6">
          {/* Profile Section */}
          <div className="bg-dark-800 rounded-lg border border-dark-700 p-6">
            <h2 className="text-lg font-medium text-gray-100 mb-4">Profile</h2>
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <UserCircleIcon className="w-16 h-16 text-gray-500 shrink-0" />
                <div className="space-y-2">
                  {name && (
                    <div>
                      <span className="text-xs text-gray-500 uppercase tracking-wide">Name</span>
                      <p className="text-gray-100 font-medium">{name}</p>
                    </div>
                  )}
                  {email && (
                    <div>
                      <span className="text-xs text-gray-500 uppercase tracking-wide">Email</span>
                      <p className="text-gray-300">{email}</p>
                    </div>
                  )}
                  <div>
                    <span className="text-xs text-gray-500 uppercase tracking-wide">Tenant</span>
                    <p className="text-gray-300 font-mono text-sm">{tenant_id}</p>
                  </div>
                  {roles.length > 0 && (
                    <div>
                      <span className="text-xs text-gray-500 uppercase tracking-wide">Roles</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {roles.map((role) => (
                          <span
                            key={role}
                            className="px-2 py-0.5 bg-primary/20 text-primary text-xs rounded-full font-medium"
                          >
                            {role}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Preferences Section */}
          <div className="bg-dark-800 rounded-lg border border-dark-700 p-6">
            <h2 className="text-lg font-medium text-gray-100 mb-4">Preferences</h2>
            <div className="space-y-4">
              {/* Timezone Setting */}
              <div>
                <label htmlFor="timezone" className="block text-sm font-medium text-gray-300 mb-2">
                  Timezone
                </label>
                <select
                  id="timezone"
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                  className="block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-hidden focus:ring-2 focus:ring-primary focus:border-primary rounded-md bg-dark-700 border-dark-600 text-gray-300"
                >
                  {timezones.map((tz) => (
                    <option key={tz} value={tz}>
                      {tz} ({moment.tz(tz).format('Z')})
                    </option>
                  ))}
                </select>
                <p className="mt-2 text-sm text-gray-400">
                  Current time: {moment().tz(timezone).format('LLLL')}
                </p>
              </div>
            </div>
          </div>

          {/* Additional Settings Section - Placeholder for future */}
          <div className="bg-dark-800 rounded-lg border border-dark-700 p-6">
            <h2 className="text-lg font-medium text-gray-100 mb-4">Notifications</h2>
            <div className="text-sm text-gray-400">Notification settings coming soon</div>
          </div>
        </div>
      </div>
    </div>
  );
};
