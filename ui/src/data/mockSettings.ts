import { staticMockData } from './staticMockData';

// Goals & Expectations Types
export interface GoalField {
  id: string;
  label: string;
  value: string;
  lastModifiedBy: string;
  lastModifiedAt: Date;
}

// User Feedback Types
export interface FeedbackItem {
  id: string;
  text: string;
  providedBy: string;
  relatedAlert: string;
  severity: 'low' | 'medium' | 'high';
  dateTime: Date;
  lastModified: Date;
  lastModifiedBy: string;
}

// Runbook Types
export interface Runbook {
  id: string;
  name: string;
  type: 'System' | 'Custom';
  description: string;
  lastUpdated: Date;
  lastUpdatedBy: string;
  content: string;
  isLocked: boolean;
  lockedBy?: string;
}

// Internal Knowledge Types
export interface SystemSource {
  id: string;
  name: string;
  reliabilityScore: number;
  comments: string;
  lastUpdated: Date;
  lastUpdatedBy: string;
}

// Users & Assets Types
export interface CriticalResource {
  id: string;
  name: string;
  type: 'User' | 'Asset';
  criticalityLevel: 'Low' | 'Medium' | 'High' | 'Critical';
  location: string;
  lastModified: Date;
  lastModifiedBy: string;
  description: string;
}

// Historical Alerts Types
export interface HistoricalReport {
  id: string;
  title: string;
  uploadDate: Date;
  uploadedBy: string;
  fileFormat: 'txt' | 'md' | 'pdf' | 'doc';
  size: string;
  summary: string;
}

// Mock Data Generators
export const generateMockFeedback = (count: number = 10): FeedbackItem[] => {
  return staticMockData.feedback.slice(0, count).map((item) => ({
    ...item,
    severity: item.severity,
    dateTime: new Date(item.dateTime),
    lastModified: new Date(item.lastModified),
  }));
};

export const generateMockRunbooks = (count: number = 5): Runbook[] => {
  return staticMockData.runbooks.slice(0, count).map((item) => ({
    ...item,
    type: item.type,
    lastUpdated: new Date(item.lastUpdated),
  }));
};

export const generateMockSources = (count: number = 8): SystemSource[] => {
  return staticMockData.sources.slice(0, count).map((item) => ({
    ...item,
    lastUpdated: new Date(item.lastUpdated),
  }));
};

export const generateMockCriticalResources = (count: number = 15): CriticalResource[] => {
  return staticMockData.criticalResources.slice(0, count).map((item) => ({
    ...item,
    type: item.type,
    criticalityLevel: item.criticalityLevel,
    lastModified: new Date(item.lastModified),
  }));
};

export const generateMockHistoricalReports = (count: number = 12): HistoricalReport[] => {
  return staticMockData.historicalReports.slice(0, count).map((item) => ({
    ...item,
    fileFormat: item.fileFormat,
    uploadDate: new Date(item.uploadDate),
  }));
};
