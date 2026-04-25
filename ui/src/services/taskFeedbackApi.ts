import type {
  TaskFeedback,
  TaskFeedbackCreate,
  TaskFeedbackUpdate,
  TaskFeedbackListResponse,
} from '../types/taskFeedback';

import { withApi, fetchList, mutateOne, apiDelete } from './apiClient';

export const getTaskFeedback = async (taskComponentId: string): Promise<TaskFeedbackListResponse> =>
  withApi('getTaskFeedback', 'fetching task feedback', () =>
    fetchList<'feedbacks', TaskFeedback>(`/tasks/${taskComponentId}/feedback`, 'feedbacks')
  );

export const createTaskFeedback = async (
  taskComponentId: string,
  data: TaskFeedbackCreate
): Promise<TaskFeedback> =>
  withApi('createTaskFeedback', 'creating task feedback', () =>
    mutateOne<TaskFeedback>('post', `/tasks/${taskComponentId}/feedback`, data)
  );

export const updateTaskFeedback = async (
  taskComponentId: string,
  feedbackId: string,
  data: TaskFeedbackUpdate
): Promise<TaskFeedback> =>
  withApi('updateTaskFeedback', 'updating task feedback', () =>
    mutateOne<TaskFeedback>('patch', `/tasks/${taskComponentId}/feedback/${feedbackId}`, data)
  );

export const deleteTaskFeedback = async (
  taskComponentId: string,
  feedbackId: string
): Promise<void> =>
  withApi('deleteTaskFeedback', 'deleting task feedback', () =>
    apiDelete(`/tasks/${taskComponentId}/feedback/${feedbackId}`)
  );
