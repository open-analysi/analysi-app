import { IntegrationGroup, IntegrationStatus } from '../types/integration';

export const mockIntegrations: IntegrationGroup[] = [
  {
    type: 'SIEM',
    description: 'Connect to SIEM platforms to monitor and analyze security events',
    integrations: [
      { id: 'splunk', name: 'Splunk', type: 'SIEM', status: IntegrationStatus.Connected },
      { id: 'sumologic', name: 'SumoLogic', type: 'SIEM', status: IntegrationStatus.NotConnected },
    ],
  },
  {
    type: 'SOAR',
    description: 'Connect to SOAR platforms to automate incident response and remediation',
    integrations: [
      { id: 'splunk-soar', name: 'Splunk SOAR', type: 'SOAR', status: IntegrationStatus.Connected },
      { id: 'tines', name: 'Tines', type: 'SOAR', status: IntegrationStatus.NotConnected },
    ],
  },
  {
    type: 'Ticketing',
    description: 'Connect to ticketing systems to create and manage incidents',
    integrations: [
      { id: 'jira', name: 'JIRA', type: 'Ticketing', status: IntegrationStatus.NotConnected },
    ],
  },
  {
    type: 'EDR',
    description:
      'Connect to endpoint detection and response platforms to monitor and respond to threats',
    integrations: [
      {
        id: 'crowdstrike',
        name: 'CrowdStrike',
        type: 'EDR',
        status: IntegrationStatus.NotConnected,
      },
    ],
  },
  {
    type: 'Messaging',
    description: 'Connect to messaging platforms to send and receive messages',
    integrations: [
      { id: 'slack', name: 'Slack', type: 'Messaging', status: IntegrationStatus.Connected },
      { id: 'gmail', name: 'Gmail', type: 'Messaging', status: IntegrationStatus.Connected },
    ],
  },
  {
    type: 'CMDB',
    description: 'Connect to CMDB platforms to manage and track assets',
    integrations: [
      { id: 'servicenow', name: 'ServiceNow', type: 'CMDB', status: IntegrationStatus.Connected },
    ],
  },
  {
    type: 'Vulnerability Management',
    description:
      'Connect to vulnerability management platforms to assess and monitor security vulnerabilities',
    integrations: [
      {
        id: 'Tenable',
        name: 'Tenable',
        type: 'Vulnerability Management',
        description: 'Access vulnerability data and scan results from Tenable.io and Tenable.sc',
        icon: '/icons/tenable.svg',
        status: IntegrationStatus.Connected,
        isConfigured: false,
      },
      {
        id: 'Qualys',
        name: 'Qualys',
        type: 'Vulnerability Management',
        description: 'Retrieve vulnerability findings and asset data from Qualys Cloud Platform',
        icon: '/icons/qualys.svg',
        status: IntegrationStatus.NotConnected,
        isConfigured: false,
      },
    ],
  },
];
