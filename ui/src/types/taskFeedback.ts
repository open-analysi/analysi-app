export type { TaskFeedback, TaskFeedbackCreate, TaskFeedbackUpdate } from './api';

export interface TaskFeedbackListResponse {
  feedbacks: import('./api').TaskFeedback[];
  total: number;
}
