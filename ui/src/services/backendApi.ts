/**
 * Backend API - Unified re-export
 *
 * This file composes all domain-specific API modules into a single `backendApi` object
 * for backward compatibility. All consumers import `{ backendApi }` from this file.
 *
 * Domain modules:
 * - alertsApi: Alerts, analysis, dispositions
 * - artifactsApi: Artifacts, downloads, enrichment
 * - integrationsApi: Integrations, connectors, schedules, credentials
 * - knowledgeApi: Knowledge units, modules, KDG graph, documents
 * - settingsApi: Analysis groups, routing rules, audit trail
 * - skillsApi: Skills, documents, content reviews
 * - tasksApi: Tasks CRUD, execution, generation
 * - workflowsApi: Workflows CRUD, runs, generation
 */

import * as alerts from './alertsApi';
import * as artifacts from './artifactsApi';
import * as controlEvents from './controlEventsApi';
import * as integrations from './integrationsApi';
import * as knowledge from './knowledgeApi';
import * as settings from './settingsApi';
import * as skills from './skillsApi';
import * as taskFeedback from './taskFeedbackApi';
import * as tasks from './tasksApi';
import * as users from './usersApi';
import * as workflows from './workflowsApi';

export const backendApi = {
  ...knowledge,
  ...tasks,
  ...workflows,
  ...alerts,
  ...integrations,
  ...settings,
  ...artifacts,
  ...skills,
  ...controlEvents,
  ...taskFeedback,
  ...users,
};

// Re-export infrastructure utilities for convenience
export {
  backendApiClient,
  isValidUuid,
  BUILTIN_TEMPLATE_UUIDS,
  resolveNodeTemplateId,
} from './apiClient';
