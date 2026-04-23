export type DispositionCategory =
  | 'True Positive (Malicious)'
  | 'True Positive (Policy Violation)'
  | 'False Positive'
  | 'Security Testing / Expected Activity'
  | 'Benign Explained'
  | 'Indeterminate / Needs Further Investigation';

export type DispositionSubcategory =
  | 'Confirmed Compromise'
  | 'Blocked/Prevented'
  | 'Confirmed Unauthorized Activity'
  | 'Benign and Alerted in Error'
  | 'Benign but Misconfigured Detection'
  | 'Red Team or Pentest'
  | 'Compliance / Audit'
  | 'Known Business Process'
  | 'Environmental Noise'
  | 'Suspicious, Not Confirmed';

export interface DispositionDetails {
  category: DispositionCategory;
  subcategory: DispositionSubcategory;
  description: string;
}

export const DISPOSITION_DETAILS: Record<DispositionSubcategory, DispositionDetails> = {
  'Confirmed Compromise': {
    category: 'True Positive (Malicious)',
    subcategory: 'Confirmed Compromise',
    description:
      'Activity definitively recognized as malicious and successful (e.g., system compromise, data exfiltration).',
  },
  'Blocked/Prevented': {
    category: 'True Positive (Malicious)',
    subcategory: 'Blocked/Prevented',
    description:
      'Malicious activity that was successfully detected and blocked, with no impact beyond the attempted intrusion.',
  },
  'Confirmed Unauthorized Activity': {
    category: 'True Positive (Policy Violation)',
    subcategory: 'Confirmed Unauthorized Activity',
    description:
      'Non-malicious but unauthorized activity violating organizational policies or security standards (e.g., installing unapproved software, off-policy network scanning).',
  },
  'Benign and Alerted in Error': {
    category: 'False Positive',
    subcategory: 'Benign and Alerted in Error',
    description:
      'The alert triggered incorrectly, with no malicious or policy-violating activity behind it (e.g., known clean process misidentified).',
  },
  'Benign but Misconfigured Detection': {
    category: 'False Positive',
    subcategory: 'Benign but Misconfigured Detection',
    description:
      'The detection logic needs tuning because the alert frequently flags legitimate processes (often a leading cause of noise in SOCs).',
  },
  'Red Team or Pentest': {
    category: 'Security Testing / Expected Activity',
    subcategory: 'Red Team or Pentest',
    description: 'Malicious-looking activity that is part of an authorized test.',
  },
  'Compliance / Audit': {
    category: 'Security Testing / Expected Activity',
    subcategory: 'Compliance / Audit',
    description:
      'Expected scanning or validation activity (e.g., vulnerability scans, compliance checks).',
  },
  'Known Business Process': {
    category: 'Benign Explained',
    subcategory: 'Known Business Process',
    description:
      'Legitimate activity critical to business operations (e.g., data backups, automated script activity).',
  },
  'Environmental Noise': {
    category: 'Benign Explained',
    subcategory: 'Environmental Noise',
    description:
      'Repeated low-level triggers (like routine network probes) that pose no threat, but may appear suspicious at a high level.',
  },
  'Suspicious, Not Confirmed': {
    category: 'Indeterminate / Needs Further Investigation',
    subcategory: 'Suspicious, Not Confirmed',
    description:
      'Activity that has some indicators of malicious intent but lacks enough evidence to be confirmed. Often requires deeper forensic analysis or correlation with additional alerts.',
  },
};

// Helper function to get all disposition categories and subcategories
export const getDispositionOptions = (): {
  category: DispositionCategory;
  subcategories: DispositionSubcategory[];
}[] => {
  const dispositionMap = new Map<DispositionCategory, DispositionSubcategory[]>();

  for (const { category, subcategory } of Object.values(DISPOSITION_DETAILS)) {
    if (!dispositionMap.has(category)) {
      dispositionMap.set(category, []);
    }
    dispositionMap.get(category)?.push(subcategory);
  }

  return [...dispositionMap.entries()].map(([category, subcategories]) => ({
    category,
    subcategories,
  }));
};

// Helper function to get the color for a disposition based on its category and subcategory
export const getDispositionColor = (disposition: string): string => {
  if (disposition === '-') return 'bg-gray-700 text-gray-300';

  // Special case for specific subcategories
  if (disposition === 'Blocked/Prevented' || disposition.includes('Blocked/Prevented')) {
    return 'bg-yellow-600 text-white';
  }

  if (disposition === 'Confirmed Compromise' || disposition.includes('Confirmed Compromise')) {
    return 'bg-red-600 text-white';
  }

  // Handle the rest based on category
  for (const details of Object.values(DISPOSITION_DETAILS)) {
    if (
      disposition === details.category ||
      disposition === details.subcategory ||
      disposition.includes(details.category) ||
      disposition.includes(details.subcategory)
    ) {
      switch (details.category) {
        case 'True Positive (Malicious)': {
          // This is a fallback - specific subcategories are handled above
          return 'bg-red-600 text-white';
        }
        case 'True Positive (Policy Violation)': {
          return 'bg-orange-600 text-white';
        }
        case 'False Positive': {
          return 'bg-green-600 text-white';
        }
        case 'Security Testing / Expected Activity': {
          return 'bg-blue-600 text-white';
        }
        case 'Benign Explained': {
          return 'bg-teal-600 text-white';
        }
        case 'Indeterminate / Needs Further Investigation': {
          return 'bg-yellow-600 text-white';
        }
      }
    }
  }

  return 'bg-gray-600 text-white';
};
