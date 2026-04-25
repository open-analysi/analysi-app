import { withApi, fetchOne, fetchList } from './apiClient';

export interface UserProfile {
  id: string;
  email: string;
  display_name: string | null;
}

export const getCurrentUser = async (): Promise<UserProfile> =>
  withApi('getCurrentUser', 'fetching current user profile', () =>
    fetchOne<UserProfile>('/users/me')
  );

export const resolveUsers = async (ids: string[]): Promise<UserProfile[]> =>
  withApi(
    'resolveUsers',
    'resolving user UUIDs',
    async () => {
      if (ids.length === 0) return [];

      const result = await fetchList<'users', UserProfile>('/users/resolve', 'users', {
        params: { ids },
        paramsSerializer: {
          indexes: null, // serialize as ids=uuid1&ids=uuid2
        },
      });
      return result.users;
    },
    { params: { count: ids.length } }
  );
