#!/usr/bin/env tsx
/**
 * Script to generate static mock data for development/demo purposes
 * This replaces runtime faker usage to keep faker out of the production bundle
 *
 * Run with: npx tsx scripts/generateMockData.ts
 */

import { faker } from '@faker-js/faker';
import fs from 'fs';
import path from 'path';

// Set a seed for consistent data generation (optional)
faker.seed(12345);

// Generate mock configuration versions
const generateMockVersions = (count: number = 10) => {
  return Array.from({ length: count }, (_, index) => ({
    id: faker.string.uuid(),
    timestamp: faker.date.recent({ days: 30 }).toISOString(),
    author: faker.internet.username(),
    changes: Array.from({ length: faker.number.int({ min: 1, max: 4 }) }, () => ({
      component: faker.helpers.arrayElement([
        'Goals & Expectations',
        'User Feedback',
        'Runbooks',
        'Internal Knowledge',
        'Users & Assets',
      ]),
      field: faker.helpers.arrayElement([
        'businessType',
        'topRisks',
        'alertRules',
        'systemConfig',
        'userAccess',
      ]),
      oldValue: faker.lorem.words(3),
      newValue: faker.lorem.words(3),
    })),
    comment: faker.helpers.arrayElement([
      'Updated business goals',
      'Modified alert rules',
      'Added new user permissions',
      'Changed system configuration',
      undefined,
    ]),
  }));
};

// Generate mock audit logs
const generateMockAuditLogs = (count: number = 20) => {
  return Array.from({ length: count }, () => ({
    id: faker.string.uuid(),
    timestamp: faker.date.recent({ days: 14 }).toISOString(),
    user: faker.internet.username(),
    action: faker.helpers.arrayElement(['view', 'edit', 'revert']),
    component: faker.helpers.arrayElement([
      'Goals & Expectations',
      'User Feedback',
      'Runbooks',
      'Internal Knowledge',
      'Users & Assets',
    ]),
    details: faker.helpers.arrayElement([
      'Viewed configuration settings',
      'Modified alert thresholds',
      'Reverted to previous version',
      'Updated user access controls',
      'Changed system parameters',
    ]),
  }));
};

// Generate mock feedback
const generateMockFeedback = (count: number = 10) => {
  return Array.from({ length: count }, () => ({
    id: faker.string.uuid(),
    text: faker.lorem.paragraph(),
    providedBy: faker.internet.username(),
    relatedAlert: faker.string.alphanumeric(8).toUpperCase(),
    severity: faker.helpers.arrayElement(['low', 'medium', 'high']),
    dateTime: faker.date.recent({ days: 30 }).toISOString(),
    lastModified: faker.date.recent({ days: 5 }).toISOString(),
    lastModifiedBy: faker.person.fullName(),
  }));
};

// Generate mock runbooks
const generateMockRunbooks = (count: number = 5) => {
  return Array.from({ length: count }, () => ({
    id: faker.string.uuid(),
    name: `${faker.hacker.adjective()} ${faker.hacker.noun()} Investigation`,
    type: faker.helpers.arrayElement(['System', 'Custom']),
    description: faker.lorem.sentence(),
    lastUpdated: faker.date.recent({ days: 14 }).toISOString(),
    lastUpdatedBy: faker.person.fullName(),
    content: faker.lorem.paragraphs(3),
    isLocked: faker.datatype.boolean(),
    lockedBy: faker.datatype.boolean() ? faker.person.fullName() : undefined,
  }));
};

// Generate mock sources
const generateMockSources = (count: number = 8) => {
  return Array.from({ length: count }, () => ({
    id: faker.string.uuid(),
    name: faker.company.name(),
    reliabilityScore: faker.number.int({ min: 1, max: 100 }),
    comments: faker.lorem.sentence(),
    lastUpdated: faker.date.recent({ days: 30 }).toISOString(),
    lastUpdatedBy: faker.person.fullName(),
  }));
};

// Generate mock critical resources
const generateMockCriticalResources = (count: number = 15) => {
  return Array.from({ length: count }, () => ({
    id: faker.string.uuid(),
    name: faker.helpers.arrayElement([faker.internet.username(), faker.system.fileName()]),
    type: faker.helpers.arrayElement(['User', 'Asset']),
    criticalityLevel: faker.helpers.arrayElement(['Low', 'Medium', 'High', 'Critical']),
    location: faker.location.city(),
    lastModified: faker.date.recent({ days: 20 }).toISOString(),
    lastModifiedBy: faker.person.fullName(),
    description: faker.lorem.sentence(),
  }));
};

// Generate mock historical reports
const generateMockHistoricalReports = (count: number = 12) => {
  return Array.from({ length: count }, () => ({
    id: faker.string.uuid(),
    title: `${faker.company.buzzNoun()} Alert Analysis`,
    uploadDate: faker.date.recent({ days: 45 }).toISOString(),
    uploadedBy: faker.person.fullName(),
    fileFormat: faker.helpers.arrayElement(['txt', 'md', 'pdf', 'doc']),
    size: `${faker.number.int({ min: 100, max: 9999 })}KB`,
    summary: faker.lorem.paragraph(),
  }));
};

// Generate all mock data
const mockData = {
  versions: generateMockVersions(10),
  auditLogs: generateMockAuditLogs(20),
  feedback: generateMockFeedback(10),
  runbooks: generateMockRunbooks(5),
  sources: generateMockSources(8),
  criticalResources: generateMockCriticalResources(15),
  historicalReports: generateMockHistoricalReports(12),
};

// Write to file
const outputPath = path.join(process.cwd(), 'src', 'data', 'staticMockData.ts');

const fileContent = `/**
 * Static mock data generated by scripts/generateMockData.ts
 * DO NOT EDIT THIS FILE MANUALLY
 *
 * To regenerate: npm run generate-mocks
 */

export const staticMockData = ${JSON.stringify(mockData, null, 2)} as const;
`;

fs.writeFileSync(outputPath, fileContent, 'utf-8');

console.log('✅ Mock data generated successfully!');
console.log(`📁 Output: ${outputPath}`);
console.log(`📊 Generated ${Object.keys(mockData).length} data collections`);
console.log('   - versions:', mockData.versions.length);
console.log('   - auditLogs:', mockData.auditLogs.length);
console.log('   - feedback:', mockData.feedback.length);
console.log('   - runbooks:', mockData.runbooks.length);
console.log('   - sources:', mockData.sources.length);
console.log('   - criticalResources:', mockData.criticalResources.length);
console.log('   - historicalReports:', mockData.historicalReports.length);
