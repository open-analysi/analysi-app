import { useState } from 'react';

import { useSettingsStore } from '../../store/settingsStore';
import AuditTrail from '../common/AuditTrail';

interface GoalField {
  id: string;
  label: string;
  value: string;
  lastModifiedBy: string;
  lastModifiedAt: Date;
}

interface SaveValues {
  businessType: string;
  topRisks: string;
}

const GoalsExpectations = () => {
  const { saveVersion } = useSettingsStore();
  const [fields, setFields] = useState<GoalField[]>([
    {
      id: 'businessType',
      label: 'Business Type',
      value: '',
      lastModifiedBy: 'John Doe',
      lastModifiedAt: new Date(),
    },
    {
      id: 'topRisks',
      label: 'Top 3 Business Risks',
      value: '',
      lastModifiedBy: 'John Doe',
      lastModifiedAt: new Date(),
    },
  ]);

  const handleChange = (id: string, value: string) => {
    setFields(
      fields.map((field) =>
        field.id === id ? { ...field, value, lastModifiedAt: new Date() } : field
      )
    );
  };

  const handleSave = (newValues: SaveValues) => {
    const changes = fields.map((field) => ({
      component: 'GoalsExpectations',
      field: field.id,
      oldValue: field.value,
      newValue: newValues[field.id as keyof SaveValues],
    }));

    saveVersion(changes, 'Updated business goals');
    // Audit logging is now automatic via interceptor
  };

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-6">
        <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">
          Goals & Expectations
        </h2>

        {fields.map((field) => (
          <div key={field.id} className="mb-6">
            <label
              htmlFor={field.id}
              className="block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              {field.label}
            </label>
            <div className="mt-1">
              <textarea
                id={field.id}
                name={field.id}
                rows={3}
                className="shadow-xs focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border border-gray-300 dark:border-gray-600 rounded-md dark:bg-gray-700"
                value={field.value}
                onChange={(e) => handleChange(field.id, e.target.value)}
              />
            </div>
            <AuditTrail
              lastModifiedBy={field.lastModifiedBy}
              lastModifiedAt={field.lastModifiedAt}
            />
          </div>
        ))}

        <div className="mt-4 flex justify-end space-x-3">
          <button
            type="button"
            className="inline-flex items-center px-4 py-2 border border-[#FF3B81] text-sm font-medium rounded-md text-[#FF3B81] bg-white hover:bg-pink-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            onClick={() =>
              handleSave({
                businessType: fields.find((f) => f.id === 'businessType')?.value || '',
                topRisks: fields.find((f) => f.id === 'topRisks')?.value || '',
              })
            }
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-[#FF3B81] hover:bg-[#FF1B6B]"
          >
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );
};

export default GoalsExpectations;
