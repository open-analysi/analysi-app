export interface ConfigurationVersion {
  id: string;
  timestamp: Date;
  author: string;
  changes: {
    component: string;
    field: string;
    oldValue: unknown;
    newValue: unknown;
  }[];
  comment?: string;
}

export interface AuditLog {
  id: string;
  timestamp: Date;
  user: string;
  action: 'view' | 'edit' | 'revert';
  component: string;
  details: string;
}
