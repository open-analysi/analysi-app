import type React from 'react';

declare module '@heroicons/react/outline' {
  const content: {
    [key: string]: (props: React.SVGProps<SVGSVGElement>) => React.JSX.Element;
  };
  export const CogIcon: (props: React.SVGProps<SVGSVGElement>) => React.JSX.Element;
  export default content;
}
