import React, { useState, useRef, useEffect } from 'react';

import { DISPOSITION_DETAILS, getDispositionColor } from '../../types/disposition';

interface DispositionBadgeProps {
  value: string;
}

export const DispositionBadge: React.FC<DispositionBadgeProps> = ({ value }) => {
  const [showTooltip, setShowTooltip] = useState(false);
  const badgeRef = useRef<HTMLButtonElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  // Find matching disposition details
  const matchingDisposition = Object.values(DISPOSITION_DETAILS).find(
    (details) =>
      value === details.category ||
      value === details.subcategory ||
      value.includes(details.category) ||
      value.includes(details.subcategory)
  );

  // Position the tooltip when shown - this must be before early returns
  useEffect(() => {
    if (!showTooltip || !badgeRef.current || !tooltipRef.current || !matchingDisposition) return;

    const badgeRect = badgeRef.current.getBoundingClientRect();

    // Calculate the position
    const tooltipWidth = 400; // Fixed width
    const tooltipHeight = tooltipRef.current.offsetHeight;

    let left = badgeRect.left + badgeRect.width / 2 - tooltipWidth / 2;
    let top = badgeRect.bottom + 8; // 8px gap

    // Adjust horizontal position if needed
    if (left < 16) left = 16; // Left margin
    if (left + tooltipWidth > window.innerWidth - 16) {
      left = window.innerWidth - 16 - tooltipWidth;
    }

    // Adjust vertical position if tooltip would go off-screen
    if (top + tooltipHeight > window.innerHeight - 16) {
      // Show above badge instead
      top = badgeRect.top - tooltipHeight - 8;
    }

    // Apply the position
    tooltipRef.current.style.left = `${left}px`;
    tooltipRef.current.style.top = `${top}px`;
  }, [showTooltip, matchingDisposition]);

  // Close tooltip when clicking outside - this must be before early returns
  useEffect(() => {
    if (!showTooltip) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (
        badgeRef.current &&
        tooltipRef.current &&
        !badgeRef.current.contains(e.target as Node) &&
        !tooltipRef.current.contains(e.target as Node)
      ) {
        setShowTooltip(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showTooltip]);

  // Handle empty or undefined values
  if (!value || value === '-') {
    return <span className="text-xs text-gray-400">-</span>;
  }

  // If no match is found, just display the value as-is
  if (!matchingDisposition) {
    return (
      <span className={`px-1.5 md:px-2 py-0.5 md:py-1 rounded-full text-xs bg-gray-600 text-white`}>
        {value}
      </span>
    );
  }

  // For True Positive (Malicious), show the subcategory name to differentiate
  // between Confirmed Compromise and Blocked/Prevented
  const displayText =
    matchingDisposition.category === 'True Positive (Malicious)'
      ? matchingDisposition.subcategory
      : matchingDisposition.category;

  // For matched dispositions, show the badge with appropriate text
  return (
    <>
      <button
        ref={badgeRef}
        className={`px-1.5 md:px-2 py-0.5 md:py-1 rounded-full text-xs ${getDispositionColor(value)} cursor-help`}
        onClick={() => setShowTooltip(!showTooltip)}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        aria-label={`Disposition: ${displayText}`}
        type="button"
      >
        {displayText}
      </button>

      {showTooltip && (
        <div
          ref={tooltipRef}
          className="fixed z-9999 w-[400px] bg-dark-800 border border-dark-600 rounded-md shadow-2xl p-5"
          style={{ maxWidth: 'calc(100vw - 32px)' }}
          role="tooltip"
          aria-live="polite"
        >
          {/* Arrow pointing to badge */}
          <div
            className="absolute w-3 h-3 bg-dark-800 border-t border-l border-dark-600 transform rotate-45"
            style={{
              top: '-6px',
              left: '50%',
              marginLeft: '-6px',
            }}
          />

          <div className="font-medium text-gray-100 mb-3 text-lg border-b border-dark-600 pb-2">
            {matchingDisposition.category}
          </div>
          <div className="text-primary mb-3 font-semibold text-base">
            {matchingDisposition.subcategory}
          </div>
          <div className="text-gray-300 text-sm leading-relaxed whitespace-normal">
            {matchingDisposition.description}
          </div>
        </div>
      )}
    </>
  );
};
