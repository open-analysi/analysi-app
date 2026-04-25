import React from 'react';

export const highlightText = (text: string | undefined, searchTerm: string): React.JSX.Element => {
  if (!text || !searchTerm.trim()) return <>{text || ''}</>;

  const parts = text.split(new RegExp(`(${searchTerm})`, 'gi'));

  return (
    <>
      {parts.map((part, index) =>
        part.toLowerCase() === searchTerm.toLowerCase() ? (
          <span key={index} className="bg-primary/20 text-primary">
            {part}
          </span>
        ) : (
          <React.Fragment key={index}>{part}</React.Fragment>
        )
      )}
    </>
  );
};
