import React from 'react';

import moment from 'moment-timezone';

import { useTimezoneStore } from '../../store/timezoneStore';
import { componentStyles } from '../../styles/components';

export const TimezoneSelector: React.FC = () => {
  const { timezone, setTimezone } = useTimezoneStore();
  const timezones = moment.tz.names();

  return (
    <div className={componentStyles.card}>
      <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">
        Timezone Settings
      </h2>
      <div className="space-y-4">
        <div>
          <label
            htmlFor="timezone"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            Select Timezone
          </label>
          <select
            id="timezone"
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-hidden focus:ring-primary focus:border-primary sm:text-sm rounded-md dark:bg-dark-700 dark:border-dark-600 dark:text-gray-300"
          >
            {timezones.map((tz) => (
              <option key={tz} value={tz}>
                {tz} ({moment.tz(tz).format('Z')})
              </option>
            ))}
          </select>
          <p className="mt-2 text-sm text-gray-500">
            Current time in selected timezone: {moment().tz(timezone).format('LLLL')}
          </p>
        </div>
      </div>
    </div>
  );
};
