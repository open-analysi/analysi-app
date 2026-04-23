import React, { useState } from 'react';

import { DocumentTextIcon, GlobeAltIcon, BookOpenIcon } from '@heroicons/react/24/outline';

interface KnowledgeResource {
  id: string;
  title: string;
  type: 'Website' | 'Document' | 'Reference';
  description: string;
  url?: string;
  lastUpdated: Date;
  icon: React.ComponentType<React.ComponentProps<'svg'>>;
}

const INITIAL_RESOURCES: KnowledgeResource[] = [
  {
    id: '1',
    title: 'Security Best Practices',
    type: 'Website',
    description: 'Comprehensive guide to modern security practices and standards',
    url: 'https://example.com/security',
    lastUpdated: new Date(),
    icon: GlobeAltIcon,
  },
  {
    id: '2',
    title: 'Incident Response Playbook',
    type: 'Document',
    description: 'Step-by-step guide for handling security incidents',
    lastUpdated: new Date(),
    icon: DocumentTextIcon,
  },
  {
    id: '3',
    title: 'Industry Standards Reference',
    type: 'Reference',
    description: 'Collection of relevant industry standards and frameworks',
    lastUpdated: new Date(),
    icon: BookOpenIcon,
  },
];

const GeneralKnowledge: React.FC = () => {
  const [resources] = useState<KnowledgeResource[]>(INITIAL_RESOURCES);

  return (
    <div className="bg-gray-50 dark:bg-gray-800 shadow-sm rounded-lg p-6">
      <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">
        General Knowledge
      </h2>
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <div>
            <h3 className="text-base font-medium text-gray-900 dark:text-gray-100">
              Knowledge Base
            </h3>
            <p className="text-sm text-gray-500">Additional references and resources</p>
          </div>
          <button
            type="button"
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-[#FF3B81] hover:bg-[#FF1B6B]"
          >
            Add Resource
          </button>
        </div>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {resources.map((resource) => (
            <div
              key={resource.id}
              className="relative rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-6 py-5 shadow-xs flex items-center space-x-3 hover:border-gray-400"
            >
              <div className="shrink-0">
                <resource.icon
                  className="h-6 w-6 text-gray-600 dark:text-gray-300"
                  aria-hidden="true"
                />
              </div>
              <div className="flex-1 min-w-0">
                <a href={resource.url} className="focus:outline-hidden">
                  <span className="absolute inset-0" aria-hidden="true" />
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    {resource.title}
                  </p>
                  <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
                    {resource.description}
                  </p>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                    {resource.type} • Updated {resource.lastUpdated.toLocaleDateString()}
                  </p>
                </a>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default GeneralKnowledge;
