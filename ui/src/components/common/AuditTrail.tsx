import { format } from 'date-fns';

interface AuditTrailProps {
  lastModifiedBy: string;
  lastModifiedAt: Date;
  note?: string;
}

const AuditTrail = ({ lastModifiedBy, lastModifiedAt, note }: AuditTrailProps) => {
  return (
    <div className="text-xs text-gray-500 dark:text-gray-400 mt-2">
      <span>
        Last edited by {lastModifiedBy} on {format(lastModifiedAt, 'MMM d, yyyy HH:mm')}
      </span>
      {note && <span className="ml-2">- {note}</span>}
    </div>
  );
};

export default AuditTrail;
