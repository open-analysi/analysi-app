import React, { useCallback, useEffect, useRef, useState } from 'react';

import {
  ArrowPathIcon,
  BeakerIcon,
  ChevronDownIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import type {
  ControlEvent,
  ControlEventChannel,
  ControlEventStatus,
} from '../../types/controlEvents';

const STATUS_STYLES: Record<ControlEventStatus, string> = {
  pending: 'bg-gray-500/20 text-gray-400',
  claimed: 'bg-yellow-500/20 text-yellow-400',
  completed: 'bg-green-500/20 text-green-400',
  failed: 'bg-red-500/20 text-red-400',
};

const TERMINAL_STATUSES: ControlEventStatus[] = ['completed', 'failed'];

function StatusBadge({ status }: { readonly status: ControlEventStatus }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${STATUS_STYLES[status]}`}
    >
      {status}
    </span>
  );
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export const ControlEventHistory: React.FC = () => {
  const { handleError, runSafe, createContext } = useErrorHandler('ControlEventHistory');

  // History state
  const [events, setEvents] = useState<ControlEvent[]>([]);
  const [channels, setChannels] = useState<ControlEventChannel[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  // Filters
  const [filterChannel, setFilterChannel] = useState('');
  const [filterStatus, setFilterStatus] = useState<ControlEventStatus | ''>('');
  const [filterDays, setFilterDays] = useState(7);

  // Test panel state
  const [showTestPanel, setShowTestPanel] = useState(false);
  const [testChannel, setTestChannel] = useState('');
  const [testPayload, setTestPayload] = useState<Record<string, string>>({});
  const [isFiring, setIsFiring] = useState(false);
  const [testEvent, setTestEvent] = useState<ControlEvent | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => {
    return stopPolling;
  }, [stopPolling]);

  const loadEvents = useCallback(async () => {
    const params = {
      ...(filterChannel && { channel: filterChannel }),
      ...(filterStatus && { status: filterStatus }),
      limit: 100,
      since_days: filterDays,
    };
    const [result] = await runSafe(
      backendApi.getControlEvents(params),
      'loadEvents',
      createContext('loading control events')
    );
    if (result) setEvents(result.events || []);
    setIsLoading(false);
  }, [runSafe, createContext, filterChannel, filterStatus, filterDays]);

  const loadChannels = useCallback(async () => {
    const [result] = await runSafe(
      backendApi.getControlEventChannels(),
      'loadChannels',
      createContext('loading channels')
    );
    if (result) setChannels(result.channels || []);
  }, [runSafe, createContext]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadChannels();
  }, [loadChannels]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadEvents();
  }, [loadEvents]);

  // When test channel changes, reset payload fields to match the channel's payload_fields
  useEffect(() => {
    if (!testChannel) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setTestPayload({});
      return;
    }
    const channelMeta = channels.find((c) => c.channel === testChannel);
    const fields = channelMeta?.payload_fields ?? [];
    setTestPayload(Object.fromEntries(fields.map((f) => [f, ''])));
  }, [testChannel, channels]);

  const startPolling = useCallback(
    (eventId: string) => {
      stopPolling();
      // eslint-disable-next-line @typescript-eslint/no-misused-promises
      pollRef.current = setInterval(async () => {
        const [result] = await runSafe(
          backendApi.getControlEvent(eventId),
          'pollEvent',
          createContext('polling event status', { entityId: eventId })
        );
        if (result) {
          setTestEvent(result);
          if (TERMINAL_STATUSES.includes(result.status as ControlEventStatus)) {
            stopPolling();
            setIsLoading(true);
            void loadEvents();
          }
        }
      }, 5000);
    },
    [runSafe, createContext, stopPolling, loadEvents]
  );

  const handleFireEvent = async () => {
    if (!testChannel) return;
    setIsFiring(true);
    stopPolling();
    setTestEvent(null);

    const payload: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(testPayload)) {
      if (v.trim()) payload[k] = v.trim();
    }

    const [result, error] = await runSafe(
      backendApi.createControlEvent({ channel: testChannel, payload }),
      'fireEvent',
      createContext('firing test event', { params: { channel: testChannel } })
    );

    if (error) {
      handleError(error, createContext('firing test event'));
    } else if (result) {
      setTestEvent(result);
      setIsLoading(true);
      void loadEvents();
      if (!TERMINAL_STATUSES.includes(result.status as ControlEventStatus)) {
        startPolling(result.id);
      }
    }
    setIsFiring(false);
  };

  const toggleExpanded = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const testChannelMeta = channels.find((c) => c.channel === testChannel);

  const renderTableBody = (): React.JSX.Element => {
    if (isLoading && events.length === 0) {
      return (
        <tr>
          <td colSpan={5} className="px-5 py-8 text-center text-gray-400">
            <ArrowPathIcon className="h-5 w-5 animate-spin mx-auto mb-2" />
            Loading events…
          </td>
        </tr>
      );
    }
    if (events.length === 0) {
      return (
        <tr>
          <td colSpan={5} className="px-5 py-10 text-center text-gray-500 text-sm">
            No events found for the selected filters.
          </td>
        </tr>
      );
    }
    return (
      <>
        {events.map((event) => {
          const isExpanded = expandedIds.has(event.id);
          return (
            <React.Fragment key={event.id}>
              <tr
                className="hover:bg-gray-800/30 cursor-pointer"
                onClick={() => toggleExpanded(event.id)}
              >
                <td className="pl-5 py-3">
                  {isExpanded ? (
                    <ChevronDownIcon className="h-3.5 w-3.5 text-gray-400" />
                  ) : (
                    <ChevronRightIcon className="h-3.5 w-3.5 text-gray-400" />
                  )}
                </td>
                <td className="px-5 py-3">
                  <span className="text-sm text-gray-300">{event.channel}</span>
                </td>
                <td className="px-5 py-3">
                  <StatusBadge status={event.status as ControlEventStatus} />
                </td>
                <td className="px-5 py-3">
                  <span className="text-sm text-gray-400">{event.retry_count}</span>
                </td>
                <td className="px-5 py-3">
                  <span className="text-sm text-gray-400">{formatDate(event.created_at)}</span>
                </td>
              </tr>
              {isExpanded && (
                <tr className="bg-gray-900/50">
                  <td colSpan={5} className="px-8 py-4">
                    <div className="space-y-2">
                      <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">
                        Event ID
                      </p>
                      <p className="text-xs text-gray-300 font-mono">{event.id}</p>
                      <p className="text-xs text-gray-500 font-medium uppercase tracking-wider mt-3">
                        Payload
                      </p>
                      <pre className="text-xs text-gray-300 bg-gray-900 rounded p-3 overflow-x-auto">
                        {JSON.stringify(event.payload, null, 2)}
                      </pre>
                    </div>
                  </td>
                </tr>
              )}
            </React.Fragment>
          );
        })}
      </>
    );
  };

  return (
    <div className="space-y-5">
      {/* Test Panel */}
      <div className="border border-gray-700 rounded-lg overflow-hidden">
        <button
          onClick={() => setShowTestPanel((v) => !v)}
          className="w-full flex items-center justify-between px-5 py-3 bg-gray-800/50 hover:bg-gray-800/70 transition-colors text-left"
        >
          <div className="flex items-center gap-2">
            <BeakerIcon className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium text-gray-200">Fire Test Event</span>
            <span className="text-xs text-gray-500">
              — trigger a rule without waiting for a real analysis
            </span>
          </div>
          {showTestPanel ? (
            <ChevronDownIcon className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronRightIcon className="h-4 w-4 text-gray-400" />
          )}
        </button>

        {showTestPanel && (
          <div className="px-5 py-4 bg-gray-800/20 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Channel picker */}
              <div className="space-y-1.5">
                <label htmlFor="test-channel" className="block text-sm font-medium text-gray-300">
                  Channel
                </label>
                <select
                  id="test-channel"
                  value={testChannel}
                  onChange={(e) => setTestChannel(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-gray-100 text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                >
                  <option value="">Select a channel…</option>
                  {channels.map((c) => (
                    <option key={c.channel} value={c.channel}>
                      {c.channel}
                    </option>
                  ))}
                </select>
                {testChannelMeta?.description && (
                  <p className="text-xs text-gray-500">{testChannelMeta.description}</p>
                )}
              </div>

              {/* Payload fields */}
              {testChannel && Object.keys(testPayload).length > 0 && (
                <div className="md:col-span-2 space-y-2">
                  <span className="block text-sm font-medium text-gray-300">
                    Payload fields
                    <span className="ml-1 text-gray-500 font-normal">(optional hints)</span>
                  </span>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    {Object.keys(testPayload).map((field) => (
                      <div key={field} className="space-y-0.5">
                        <label className="block text-xs text-gray-500">{field}</label>
                        <input
                          type="text"
                          value={testPayload[field]}
                          onChange={(e) =>
                            setTestPayload((p) => ({ ...p, [field]: e.target.value }))
                          }
                          className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-gray-100 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="flex items-center gap-4">
              <button
                onClick={() => void handleFireEvent()}
                disabled={!testChannel || isFiring}
                className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-md hover:bg-primary/90 disabled:opacity-50 text-sm"
              >
                <BeakerIcon className="h-4 w-4" />
                {isFiring ? 'Firing…' : 'Fire Event'}
              </button>

              {testEvent && (
                <div className="flex items-center gap-3 text-sm">
                  <span className="text-gray-400 font-mono text-xs">{testEvent.id}</span>
                  <StatusBadge status={testEvent.status as ControlEventStatus} />
                  {!TERMINAL_STATUSES.includes(testEvent.status as ControlEventStatus) && (
                    <span className="flex items-center gap-1 text-xs text-gray-500">
                      <ArrowPathIcon className="h-3 w-3 animate-spin" />
                      polling every 5s…
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* History filters */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={filterChannel}
          onChange={(e) => setFilterChannel(e.target.value)}
          className="px-3 py-1.5 bg-gray-900 border border-gray-700 rounded-md text-gray-100 text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        >
          <option value="">All channels</option>
          {channels.map((c) => (
            <option key={c.channel} value={c.channel}>
              {c.channel}
            </option>
          ))}
        </select>

        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value as ControlEventStatus | '')}
          className="px-3 py-1.5 bg-gray-900 border border-gray-700 rounded-md text-gray-100 text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        >
          <option value="">All statuses</option>
          {(['pending', 'claimed', 'completed', 'failed'] as ControlEventStatus[]).map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <select
          value={filterDays}
          onChange={(e) => setFilterDays(Number(e.target.value))}
          className="px-3 py-1.5 bg-gray-900 border border-gray-700 rounded-md text-gray-100 text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        >
          {[1, 7, 14, 30].map((d) => (
            <option key={d} value={d}>
              Last {d} {d === 1 ? 'day' : 'days'}
            </option>
          ))}
        </select>

        <button
          onClick={() => {
            setIsLoading(true);
            void loadEvents();
          }}
          disabled={isLoading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-700 text-white rounded-md hover:bg-gray-600 disabled:opacity-50 text-sm"
        >
          <ArrowPathIcon className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>

        <span className="ml-auto text-xs text-gray-500">Newest first · max 100 results</span>
      </div>

      {/* History table */}
      <div className="bg-gray-800/30 border border-gray-700 rounded-lg overflow-hidden overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-700 table-fixed">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="px-5 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider w-8" />
              <th className="px-5 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider w-1/4">
                Channel
              </th>
              <th className="px-5 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider w-28">
                Status
              </th>
              <th className="px-5 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider w-16">
                Retries
              </th>
              <th className="px-5 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">
                When
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">{renderTableBody()}</tbody>
        </table>
      </div>

      {!isLoading && events.length > 0 && (
        <p className="text-xs text-gray-500">{events.length} events</p>
      )}
    </div>
  );
};
