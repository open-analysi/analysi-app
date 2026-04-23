/**
 * Page Tracking Hook
 *
 * Automatically tracks page views and time spent on page.
 * Use this hook in page components to track user navigation.
 *
 * Example usage:
 *   usePageTracking('Alert Details', '/alerts/:id');
 */

import { useEffect, useRef } from 'react';

import { useLocation } from 'react-router';

import { trackPageView, trackPageExit } from '../utils/analyticsLogger';

export function usePageTracking(pageTitle: string, component?: string) {
  const location = useLocation();
  const enterTimeRef = useRef<number>(Date.now());
  const hasTrackedRef = useRef<boolean>(false);

  useEffect(() => {
    // Only track if we haven't tracked this mount yet
    if (!hasTrackedRef.current) {
      enterTimeRef.current = Date.now();
      trackPageView(location.pathname, pageTitle, component);
      hasTrackedRef.current = true;
    }

    // Track page exit when component unmounts
    return () => {
      if (hasTrackedRef.current) {
        const duration = Date.now() - enterTimeRef.current;
        trackPageExit(location.pathname, pageTitle, duration, component);
        hasTrackedRef.current = false;
      }
    };
    // Intentionally only depend on location.pathname to detect actual navigation
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);
}
