import React from 'react';

import { UserIcon, SparklesIcon } from '@heroicons/react/24/outline';
import Markdown from 'react-markdown';

import type { ChatMessage as ChatMessageType } from '../../types/chat';
import { getMessageText } from '../../types/chat';
import { reportMarkdownComponents } from '../alerts/markdownComponents';

/** Compact markdown overrides sized for the narrow chat panel. */
const chatMarkdownComponents = {
  ...reportMarkdownComponents,
  h1: ({ children }: { children?: React.ReactNode }) => (
    <h1 className="text-sm font-bold mb-2 text-cyan-400">{children}</h1>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h2 className="text-sm font-semibold mb-1.5 text-emerald-400">{children}</h2>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="text-sm font-medium mb-1 text-violet-400">{children}</h3>
  ),
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="mb-2 text-gray-200 text-sm leading-relaxed">{children}</p>
  ),
};

interface Props {
  message: ChatMessageType;
}

export const ChatMessage: React.FC<Props> = ({ message }) => {
  const isUser = message.role === 'user';
  const text = getMessageText(message);

  return (
    <div className={`flex gap-3 px-4 py-3 ${isUser ? '' : 'bg-dark-800/50'}`}>
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center ${
          isUser ? 'bg-dark-600 text-gray-300' : 'bg-primary/20 text-primary'
        }`}
      >
        {isUser ? <UserIcon className="w-4 h-4" /> : <SparklesIcon className="w-4 h-4" />}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-gray-400 mb-1">{isUser ? 'You' : 'Analysi'}</p>
        {isUser ? (
          <div className="text-sm text-gray-200 whitespace-pre-wrap break-words leading-relaxed">
            {text}
          </div>
        ) : (
          <div className="prose-chat text-sm break-words">
            <Markdown components={chatMarkdownComponents}>{text}</Markdown>
          </div>
        )}
      </div>
    </div>
  );
};
