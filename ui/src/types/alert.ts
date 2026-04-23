// Alert types — re-exports from generated types + UI-only types

// Re-export API types from generated types (single source of truth)
export type {
  AlertSeverity,
  AlertStatus,
  Alert,
  Disposition,
  FindingInfo,
  EvidenceArtifact,
  Observable,
  OCSFDevice,
  Actor,
  WorkflowGenerationStage,
  WorkflowGenerationStatus,
  WorkflowGenerationPhase,
  WorkflowGenerationProgress,
  WorkflowGeneration,
  ActiveWorkflowResponse,
} from './api';

export type {
  AlertAnalysisResponse as CurrentAnalysis,
  AlertAnalysisResponse as AlertAnalysis,
  AnalysisStatus as AnalysisStatusDetailed,
} from './api';

// ---- UI-only types below (no generated counterpart) ----

import type {
  Alert as GeneratedAlert,
  AlertSeverity as GeneratedAlertSeverity,
  AlertStatus as GeneratedAlertStatus,
  AnalysisStatus,
  WorkflowGeneration as GeneratedWorkflowGeneration,
  WorkflowGenerationStage as GeneratedWorkflowGenerationStage,
} from './api';

// Analysis progress response
interface StepStatus {
  status: AnalysisStatus;
  timestamp?: string;
  error?: string;
}

export interface AnalysisProgress {
  analysis_id: string;
  current_step: string;
  completed_steps: number;
  total_steps: number;
  status: AnalysisStatus;
  error?: string;
  steps_detail?: {
    [key: string]: {
      completed: boolean;
      started_at: string | null;
      completed_at: string | null;
      retries: number;
      error: string | null;
    };
  };
  // Legacy field names that might still be in use
  progress_details?: {
    pre_triage: StepStatus;
    context_retrieval: StepStatus;
    workflow_builder: StepStatus;
    workflow_execution: StepStatus;
    final_disposition_update: StepStatus;
  };
}

// API Response types (service layer shapes)
export interface AlertsListResponse {
  alerts: GeneratedAlert[];
  total: number;
  limit?: number;
  offset?: number;
  has_next?: boolean;
}

export interface AnalysisStartResponse {
  analysis_id: string;
  status: string;
  message: string;
}

// Query parameters for listing alerts
export interface AlertsQueryParams {
  // Pagination (offset/limit pattern)
  offset?: number;
  limit?: number;

  // Filtering
  severity?: GeneratedAlertSeverity[];
  source_vendor?: string;
  source_product?: string;
  analysis_status?: GeneratedAlertStatus;
  disposition_category?: string;
  min_confidence?: number;
  max_confidence?: number;

  // Time filtering
  time_from?: string;
  time_to?: string;

  // Search
  search?: string;

  // Sorting
  sort?: 'created_at' | 'severity' | 'confidence' | 'analyzed_at';
  order?: 'asc' | 'desc';
}

// Analysis artifacts
export interface AnalysisArtifact {
  id: string;
  workflow_run_id: string;
  name: string;
  content: unknown;
  created_at: string;
}

// Alert filters for UI
export interface AlertFilters {
  severity: {
    critical: boolean;
    high: boolean;
    medium: boolean;
    low: boolean;
    info: boolean;
  };
  analysisStatus: {
    not_analyzed: boolean;
    analyzing: boolean;
    analyzed: boolean;
    analysis_failed: boolean;
  };
  disposition: string[];
  sourceVendor: string[];
  sourceProduct: string[];
}

// Time range for filtering alerts
export interface TimeRange {
  startDate: Date;
  endDate: Date;
}

// Pagination state for tables
export interface PaginationState {
  currentPage: number;
  itemsPerPage: number;
  totalItems?: number;
  totalPages?: number;
}

export interface TaskProposal {
  cy_name: string;
  name: string;
  description: string;
  designation: 'existing' | 'modification' | 'new';
}

export interface StageMetrics {
  stage: GeneratedWorkflowGenerationStage;
  duration_ms: number;
  cost_usd: number;
  num_turns?: number;
}

export interface OrchestrationResults {
  runbook?: string;
  task_proposals?: TaskProposal[];
  tasks_built?: string[];
  workflow_composition?: string[];
  metrics?: {
    stages: StageMetrics[];
    total_cost_usd: number;
  };
  error?: {
    message: string;
    timestamp: string;
  };
}

export interface WorkflowGenerationListResponse {
  workflow_generations: GeneratedWorkflowGeneration[];
  total: number;
}
