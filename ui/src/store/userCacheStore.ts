import { create } from 'zustand';

import { getCurrentUser, resolveUsers, UserProfile } from '../services/usersApi';

export interface UserCacheState {
  cache: Record<string, UserProfile>;
  pendingIds: Set<string>;
  currentUser: UserProfile | null;

  fetchCurrentUser: () => Promise<void>;
  resolveUsers: (ids: string[]) => Promise<void>;
  getUserDisplay: (id: string) => string;
}

export const useUserCacheStore = create<UserCacheState>((set, get) => ({
  cache: {},
  pendingIds: new Set(),
  currentUser: null,

  fetchCurrentUser: async () => {
    try {
      const user = await getCurrentUser();
      set((state) => ({
        currentUser: user,
        cache: { ...state.cache, [user.id]: user },
      }));
    } catch {
      // Silently fail — UI will show fallback
    }
  },

  resolveUsers: async (ids: string[]) => {
    const { cache, pendingIds } = get();

    // Dedup: skip already cached or in-flight
    const newIds = ids.filter((id) => id && !cache[id] && !pendingIds.has(id));
    if (newIds.length === 0) return;

    // Cap at 50 per batch (API limit)
    const batch = newIds.slice(0, 50);

    // Mark as pending
    const nextPending = new Set(pendingIds);
    for (const id of batch) nextPending.add(id);
    set({ pendingIds: nextPending });

    try {
      const users = await resolveUsers(batch);
      set((state) => {
        const nextCache = { ...state.cache };
        for (const user of users) {
          nextCache[user.id] = user;
        }
        const nextPendingAfter = new Set(state.pendingIds);
        for (const id of batch) nextPendingAfter.delete(id);
        return { cache: nextCache, pendingIds: nextPendingAfter };
      });
    } catch {
      // Clear pending on failure so they can be retried
      set((state) => {
        const nextPendingAfter = new Set(state.pendingIds);
        for (const id of batch) nextPendingAfter.delete(id);
        return { pendingIds: nextPendingAfter };
      });
    }
  },

  getUserDisplay: (id: string) => {
    if (!id) return 'Unknown';
    const user = get().cache[id];
    if (!user) return `${id.slice(0, 8)}...`;
    return user.display_name || user.email || `${id.slice(0, 8)}...`;
  },
}));
