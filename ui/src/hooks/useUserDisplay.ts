import { useEffect } from 'react';

import { useUserCacheStore } from '../store/userCacheStore';

/**
 * Returns a human-readable display name for a user UUID.
 * Triggers async resolution if the user is not yet cached.
 * Returns a truncated UUID as placeholder while loading.
 */
export function useUserDisplay(userId: string | undefined): string {
  const getUserDisplay = useUserCacheStore((s) => s.getUserDisplay);
  const resolve = useUserCacheStore((s) => s.resolveUsers);
  const cached = useUserCacheStore((s) => (userId ? s.cache[userId] : undefined));

  useEffect(() => {
    if (userId && !cached) {
      void resolve([userId]);
    }
  }, [userId, cached, resolve]);

  if (!userId) return 'Unknown';
  return getUserDisplay(userId);
}
