import moment from 'moment-timezone';

import { useTimezoneStore } from '../store/timezoneStore';

export const useFormattedDate = () => {
  const { timezone } = useTimezoneStore();

  return {
    formatDate: (date: Date | string) => {
      return moment(date).tz(timezone).format('LLLL');
    },
    formatDateShort: (date: Date | string) => {
      return moment(date).tz(timezone).format('L LT');
    },
  };
};
