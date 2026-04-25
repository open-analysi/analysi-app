import React from 'react';

import { SparklesIcon } from '@heroicons/react/24/outline';

interface Props {
  prompts: string[];
  onSelect: (prompt: string) => void;
}

/**
 * Context-aware suggested prompt chips shown when the conversation is empty.
 */
export const SuggestedPrompts: React.FC<Props> = ({ prompts, onSelect }) => {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
      <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mb-4">
        <SparklesIcon className="w-6 h-6 text-primary" />
      </div>
      <h3 className="text-sm font-medium text-gray-300 mb-1">Analysi Assistant</h3>
      <p className="text-xs text-gray-500 mb-6 max-w-[280px]">
        Ask me anything about the Analysi platform — alerts, workflows, tasks, integrations, and
        more.
      </p>
      <div className="flex flex-col gap-2 w-full max-w-[300px]">
        {prompts.map((prompt) => (
          <button
            key={prompt}
            onClick={() => onSelect(prompt)}
            className="text-left text-xs text-gray-400 bg-dark-700 hover:bg-dark-600 hover:text-gray-200 rounded-lg px-3 py-2.5 transition-colors border border-dark-600 hover:border-dark-500"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
};
