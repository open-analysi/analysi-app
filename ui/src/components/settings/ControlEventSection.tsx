import React from 'react';

import { useUrlState } from '../../hooks/useUrlState';

import { ControlEventHistory } from './ControlEventHistory';
import { ControlEventRules } from './ControlEventRules';

const TABS = [
  { id: 'rules', label: 'Reaction Rules' },
  { id: 'history', label: 'Control Events' },
] as const;

type TabId = (typeof TABS)[number]['id'];

export const ControlEventSection: React.FC = () => {
  const [tab, setTab] = useUrlState<string>('tab', 'rules');

  return (
    <div>
      {/* Sub-tab bar */}
      <div className="border-b border-gray-700/30 mb-6">
        <div className="flex space-x-6">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                tab === t.id
                  ? 'border-primary text-white'
                  : 'border-transparent text-gray-400 hover:text-gray-200'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {(tab as TabId) === 'rules' ? <ControlEventRules /> : <ControlEventHistory />}
    </div>
  );
};
