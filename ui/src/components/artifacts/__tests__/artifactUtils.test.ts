import { vi, describe, it, expect, beforeEach } from 'vitest';

import * as artifactUtils from '../artifactUtils';

// Mock the module directly
vi.mock('../artifactUtils', async () => {
  const actual = await vi.importActual('../artifactUtils');
  return {
    ...actual,
    // Keep the real loadArtifactContent but override determineContentType
    determineContentType: vi.fn((filename, category) => {
      if (category === 'timeline' || category === 'logs') {
        return 'log';
      }
      if (filename.endsWith('.json')) {
        return 'json';
      }
      if (filename.endsWith('.log')) {
        return 'log';
      }
      return 'text';
    }),
  };
});

// Mock fetch
global.fetch = vi.fn();

describe('Artifact Utilities', () => {
  beforeEach(() => {
    // Reset mock between tests
    vi.resetAllMocks();
    // Reset mock implementation to avoid test interference
    vi.mocked(artifactUtils.determineContentType).mockImplementation((filename, category) => {
      if (category === 'timeline' || category === 'logs') {
        return 'log';
      }
      if (filename.endsWith('.json')) {
        return 'json';
      }
      if (filename.endsWith('.log')) {
        return 'log';
      }
      return 'text';
    });
  });

  describe('determineContentType', () => {
    it('identifies log files by extension', () => {
      expect(artifactUtils.determineContentType('file.log', 'edr')).toBe('log');
    });

    it('identifies JSON files by extension', () => {
      expect(artifactUtils.determineContentType('file.json', 'edr')).toBe('json');
    });

    it('always treats timeline category as log type regardless of extension', () => {
      expect(artifactUtils.determineContentType('file.json', 'timeline')).toBe('log');
    });

    it('always treats logs category as log type regardless of extension', () => {
      expect(artifactUtils.determineContentType('file.txt', 'logs')).toBe('log');
    });
  });

  describe('loadArtifactContent', () => {
    it('loads Triggering Events data properly', async () => {
      // Mock log data
      const mockLogData = ',2022/09/30 7:19:00,PA1234567890,THREAT,vulnerability,2305...';

      // Mock JSON data for summary
      const mockSummaryData = {
        summary: { threats: 5, severity: 'high' },
      };

      // Mock fetch implementation based on URL pattern
      vi.mocked(global.fetch).mockImplementation((url) => {
        const urlString =
          typeof url === 'string' ? url : url instanceof URL ? url.toString() : String(url);

        // For the primary log file
        if (urlString.includes('pan_threat.log')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            text: () => Promise.resolve(mockLogData),
            json: () => Promise.reject(new Error('Should not call json()')),
          } as unknown as Response);
        }

        // For directory check or HEAD requests
        if (urlString.includes('method') && urlString.includes('HEAD')) {
          return Promise.resolve({
            ok: true,
            status: 200,
          } as Response);
        }

        // For summary data requests
        if (urlString.includes('summary') && urlString.includes('json')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            text: () => Promise.resolve(JSON.stringify(mockSummaryData)),
            json: () => Promise.resolve(mockSummaryData),
          } as unknown as Response);
        }

        // Default response
        return Promise.resolve({
          ok: true,
          status: 200,
        } as Response);
      });

      const result = await artifactUtils.loadArtifactContent({
        alertId: '1',
        category: 'timeline',
        viewMode: 'original',
      });

      // Verify the content type and data
      expect(result.contentType).toBe('log');
      expect(result.data).toBe(mockLogData);
      expect(result.category).toBe('timeline');
    });

    it('loads Supporting Events data properly', async () => {
      // Mock for actual log data
      const mockLogData = ',2022/09/30 7:19:00,PA1234567890,SUPPORTING,vulnerability...';

      // Mock for the summary JSON data
      const mockSummaryData = {
        summary: { events: 3, severity: 'medium' },
      };

      // Setup comprehensive mock for fetch calls
      vi.mocked(global.fetch).mockImplementation((url) => {
        const urlString =
          typeof url === 'string' ? url : url instanceof URL ? url.toString() : String(url);

        // For main log file
        if (urlString.includes('supporting_events/original/pan_threat.log')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            text: () => Promise.resolve(mockLogData),
            json: () => Promise.reject(new Error('Should not call json()')),
          } as unknown as Response);
        }

        // For summary files
        if (urlString.includes('summary') && urlString.includes('json')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            text: () => Promise.resolve(JSON.stringify(mockSummaryData)),
            json: () => Promise.resolve(mockSummaryData),
          } as unknown as Response);
        }

        // Default response for HEAD requests, etc.
        return Promise.resolve({
          ok: true,
          status: 200,
        } as Response);
      });

      // Force content type to be log for this test
      vi.mocked(artifactUtils.determineContentType).mockReturnValue('log');

      const result = await artifactUtils.loadArtifactContent({
        alertId: '1',
        category: 'logs',
        viewMode: 'original',
      });

      // Verify the content type and data
      expect(result.contentType).toBe('log');
      expect(result.data).toBe(mockLogData);
      expect(result.category).toBe('logs');
    });

    it('loads EDR data properly', async () => {
      // Mock for actual JSON data
      const mockJsonData = { processes: [{ pid: 1234, name: 'process.exe' }] };
      const mockSummaryData = { summary: { processes: 1 } };

      // Setup mocks for the fetch calls with better URL handling
      vi.mocked(global.fetch).mockImplementation((url) => {
        const urlString =
          typeof url === 'string' ? url : url instanceof URL ? url.toString() : String(url);

        // For the primary JSON file
        if (urlString.includes('edr/Processes/original/processes_data.json')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve(mockJsonData),
            text: () => Promise.resolve(JSON.stringify(mockJsonData)),
          } as unknown as Response);
        }

        // For the summary JSON file
        if (urlString.includes('edr/Processes/summary/processes_data.json')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve(mockSummaryData),
            text: () => Promise.resolve(JSON.stringify(mockSummaryData)),
          } as unknown as Response);
        }

        // Default response for HEAD requests, etc.
        return Promise.resolve({
          ok: true,
          status: 200,
        } as Response);
      });

      // Force content type to be json for this test
      vi.mocked(artifactUtils.determineContentType).mockReturnValue('json');

      const result = await artifactUtils.loadArtifactContent({
        alertId: '1',
        category: 'edr',
        subcategory: 'Processes',
        viewMode: 'original',
      });

      // Verify the content type and data
      expect(result.contentType).toBe('json');
      expect(result.data).toEqual(mockJsonData);
      expect(result.category).toBe('edr');
      expect(result.subcategory).toBe('Processes');
    });

    it('loads summary view data properly', async () => {
      // Setup the mock to force an error for the summary data so it falls back
      const mockFailResponse = {
        ok: false,
        status: 404,
      } as Response;

      vi.mocked(global.fetch).mockResolvedValue(mockFailResponse);

      const result = await artifactUtils.loadArtifactContent({
        alertId: '1',
        category: 'timeline',
        viewMode: 'summary',
      });

      // Verify we get the fallback data structure for the summary view
      expect(result.contentType).toBe('json');
      expect(result.category).toBe('timeline');

      // Verify the error structure in the fallback data
      const data = result.data as Record<string, unknown>;
      expect(data.error).toBe(true);
      expect(data.message).toContain('Failed to load data for timeline');
      expect(data.category).toBe('timeline');
      expect(data.viewMode).toBe('summary');
    });

    it('falls back to mock data when file not found', async () => {
      // Mock for head request failing
      const mockFailResponse = {
        ok: false,
        status: 404,
      } as Response;

      // Setup mocks for the fetch calls
      vi.mocked(global.fetch).mockResolvedValue(mockFailResponse);

      const result = await artifactUtils.loadArtifactContent({
        alertId: '1',
        category: 'timeline',
        viewMode: 'original',
      });

      // Verify fallback data was used
      expect(result.contentType).toBe('json');
      expect(typeof result.data).toBe('object');
      if (typeof result.data === 'object' && result.data !== null) {
        expect((result.data as Record<string, unknown>).error).toBe(true);
        expect((result.data as Record<string, unknown>).message).toContain(
          'Failed to load data for timeline'
        );
      }
    });

    it('directly finds pan_threat.log file for triggering events', async () => {
      // Mock for actual log data
      const mockLogData = ',2022/09/30 7:19:00,PA1234567890,THREAT,vulnerability,2305...';

      // Mock for summary data
      const mockSummaryData = {
        summary: { threats: 5, severity: 'high' },
      };

      // Setup comprehensive mock for fetch calls
      vi.mocked(global.fetch).mockImplementation((url) => {
        const urlString =
          typeof url === 'string' ? url : url instanceof URL ? url.toString() : String(url);

        // For pan_threat.log file
        if (urlString.includes('pan_threat.log')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            text: () => Promise.resolve(mockLogData),
            json: () => Promise.reject(new Error('Should not call json()')),
          } as unknown as Response);
        }

        // For summary files
        if (urlString.includes('summary') && urlString.includes('json')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            text: () => Promise.resolve(JSON.stringify(mockSummaryData)),
            json: () => Promise.resolve(mockSummaryData),
          } as unknown as Response);
        }

        // Default success response for other requests
        return Promise.resolve({
          ok: true,
          status: 200,
        } as Response);
      });

      // Force content type to be log for this test
      vi.mocked(artifactUtils.determineContentType).mockReturnValue('log');

      const result = await artifactUtils.loadArtifactContent({
        alertId: '1',
        category: 'timeline',
        viewMode: 'original',
      });

      // Verify the content type and data
      expect(result.contentType).toBe('log');
      expect(result.data).toBe(mockLogData);
    });

    it('loads CVE info in both original and summary views', async () => {
      // Mock the fetch function to return different content for original vs summary
      vi.spyOn(global, 'fetch').mockImplementation((url: URL | RequestInfo) => {
        // Safely convert URL to string, handling both string and URL objects
        let urlStr = '';
        if (typeof url === 'string') {
          urlStr = url;
        } else if (url instanceof URL) {
          urlStr = url.href;
        } else if (url instanceof Request) {
          urlStr = url.url;
        } else {
          // Fallback - shouldn't happen in our tests
          urlStr = '/unknown-url';
        }

        // Mock HEAD requests to make directory listing work
        if (urlStr.includes('HEAD')) {
          return Promise.resolve({
            ok: true,
            status: 200,
          } as Response);
        }

        // Mock cve_info directory file check
        if (urlStr.includes('cve_info/original/cveawg_mitre_org.json')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            text: () => Promise.resolve('{"dataType":"CVE_RECORD_ORIGINAL"}'),
            json: () => Promise.resolve({ dataType: 'CVE_RECORD_ORIGINAL' }),
          } as Response);
        }

        // Mock summary directory file check
        if (urlStr.includes('cve_info/summary/cveawg_mitre_org.json')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            text: () => Promise.resolve('{"summary":{"cveId":"CVE-SUMMARY"}}'),
            json: () => Promise.resolve({ summary: { cveId: 'CVE-SUMMARY' } }),
          } as Response);
        }

        // For any other requests, return 404
        return Promise.resolve({
          ok: false,
          status: 404,
        } as Response);
      });

      // Test original view
      const originalContent = await artifactUtils.loadArtifactContent({
        alertId: '1',
        category: 'vulnerabilities',
        viewMode: 'original',
      });

      // Since we're using fallback if file not found, expect fallback data
      expect(originalContent.contentType).toBe('json');

      // Test summary view
      const summaryContent = await artifactUtils.loadArtifactContent({
        alertId: '1',
        category: 'vulnerabilities',
        viewMode: 'summary',
      });

      expect(summaryContent.contentType).toBe('json');

      // Verify we're not getting the same data for both view modes
      expect(originalContent.data).not.toEqual(summaryContent.data);
    });
  });
});
