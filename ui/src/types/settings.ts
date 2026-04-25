// Settings-related types

export type {
  AnalysisGroup,
  AnalysisGroupCreate,
  AlertRoutingRule,
  AlertRoutingRuleCreate,
} from './api';

import type { AnalysisGroup, AlertRoutingRule } from './api';

export interface AnalysisGroupListResponse {
  analysis_groups: AnalysisGroup[];
  total: number;
}

export interface AlertRoutingRuleListResponse {
  rules: AlertRoutingRule[];
  total: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
}
