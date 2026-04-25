import { useCallback, useState } from 'react';

const STORAGE_KEY = 'sidebar-collapsed';

export function useSidebarCollapse() {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'true';
    } catch {
      return false;
    }
  });

  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(STORAGE_KEY, String(next));
      } catch {
        // Silently fail if localStorage is unavailable
      }
      return next;
    });
  }, []);

  return { collapsed, toggle } as const;
}
