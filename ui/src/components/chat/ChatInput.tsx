import React, { useState, useRef, useCallback } from 'react';

import { PaperAirplaneIcon, StopIcon } from '@heroicons/react/24/solid';

interface Props {
  onSend: (content: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
}

export const ChatInput: React.FC<Props> = ({ onSend, onStop, isStreaming, disabled }) => {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || isStreaming || disabled) return;
    onSend(trimmed);
    setText('');
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [text, isStreaming, disabled, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Auto-resize textarea
  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  };

  return (
    <div className="border-t border-dark-600 p-3">
      <div className="flex items-end gap-2 bg-dark-700 rounded-lg px-3 py-2">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Ask about Analysi..."
          rows={1}
          disabled={disabled}
          className="flex-1 bg-transparent text-sm text-gray-200 placeholder-gray-500 resize-none focus:outline-none min-h-[24px] max-h-[120px]"
        />
        {isStreaming ? (
          <button
            onClick={onStop}
            className="flex-shrink-0 p-1.5 rounded-md bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
            title="Stop generating"
          >
            <StopIcon className="w-4 h-4" />
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={!text.trim() || disabled}
            className="flex-shrink-0 p-1.5 rounded-md bg-primary/20 text-primary hover:bg-primary/30 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            title="Send message"
          >
            <PaperAirplaneIcon className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
};
