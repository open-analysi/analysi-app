/**
 * Analytics Logger
 *
 * Tracks user experience events (page views, clicks, time on page)
 * for UX analytics and behavior tracking.
 *
 * This is separate from backend API audit logging - this tracks what
 * users do (pages visited, buttons clicked) rather than API calls.
 */

import { backendApi } from '../services/backendApi';
import { useAuthStore } from '../store/authStore';
import type { AuditLogCreate } from '../types/audit';

interface AnalyticsConfig {
  enabled: boolean;
  batchSize: number;
  flushInterval: number;
  maxQueueSize: number;
  consoleLogging: boolean;
}

const config: AnalyticsConfig = {
  enabled: true,
  batchSize: 5,
  flushInterval: 10000, // 10 seconds
  maxQueueSize: 20,
  consoleLogging: import.meta.env.DEV,
};

let eventQueue: AuditLogCreate[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;

// Track the last page view to prevent duplicates
let lastPageView: { route: string; pageTitle: string; timestamp: number } | null = null;
let lastPageExit: { route: string; pageTitle: string; timestamp: number } | null = null;

/**
 * Get current user session info
 */
function getSessionInfo() {
  const { email, name } = useAuthStore.getState();
  const userId = email ?? 'anonymous';
  const userName = name ?? email ?? 'Anonymous User';

  // Generate or retrieve session ID
  let sessionId = sessionStorage.getItem('analytics_session_id');
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    sessionStorage.setItem('analytics_session_id', sessionId);
  }

  return { userId, userName, sessionId };
}

/**
 * Flush queued events to backend
 */
async function flushQueue() {
  if (eventQueue.length === 0) return;

  const eventsToSend = [...eventQueue];
  eventQueue = [];

  if (flushTimer) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }

  try {
    // Send events in batch
    await Promise.all(eventsToSend.map((event) => backendApi.createAuditLog(event)));

    if (config.consoleLogging) {
      console.log('[Analytics] Flushed %d events', eventsToSend.length);
    }
  } catch (error) {
    console.error('[Analytics] Failed to flush events:', error);
    // Re-queue failed events (up to max queue size)
    eventQueue = [...eventsToSend.slice(-config.maxQueueSize), ...eventQueue].slice(
      0,
      config.maxQueueSize
    );
  }
}

/**
 * Queue an event for sending
 */
function queueEvent(event: AuditLogCreate) {
  if (!config.enabled) return;

  eventQueue.push(event);

  if (config.consoleLogging) {
    console.log('[Analytics]', event.action_type, event.action, event);
  }

  // Flush if batch size reached
  if (eventQueue.length >= config.batchSize) {
    void flushQueue();
  }
  // Or schedule a flush
  else if (!flushTimer) {
    flushTimer = setTimeout(() => void flushQueue(), config.flushInterval);
  }

  // Force flush if queue too large
  if (eventQueue.length >= config.maxQueueSize) {
    void flushQueue();
  }
}

/**
 * Track a page view
 */
export function trackPageView(route: string, pageTitle: string, component?: string) {
  const now = Date.now();

  // Prevent duplicate page views within 100ms
  if (
    lastPageView &&
    lastPageView.route === route &&
    lastPageView.pageTitle === pageTitle &&
    now - lastPageView.timestamp < 100
  ) {
    if (config.consoleLogging) {
      console.log('[Analytics] Skipping duplicate page_view for', pageTitle, 'within 100ms');
    }
    return;
  }

  lastPageView = { route, pageTitle, timestamp: now };

  const { userId, userName, sessionId } = getSessionInfo();

  const event: AuditLogCreate = {
    actor_id: userId,
    user_name: userName,
    session_id: sessionId,
    source: 'UI',
    action_type: 'page_view',
    action: `view ${pageTitle}`,
    component: component || pageTitle,
    route,
    page_title: pageTitle,
    result: 'success',
  };

  queueEvent(event);
}

/**
 * Track a page exit with duration
 */
export function trackPageExit(
  route: string,
  pageTitle: string,
  durationMs: number,
  component?: string
) {
  const now = Date.now();

  // Prevent duplicate page exits within 100ms
  if (
    lastPageExit &&
    lastPageExit.route === route &&
    lastPageExit.pageTitle === pageTitle &&
    now - lastPageExit.timestamp < 100
  ) {
    if (config.consoleLogging) {
      console.log('[Analytics] Skipping duplicate page_exit for', pageTitle, 'within 100ms');
    }
    return;
  }

  lastPageExit = { route, pageTitle, timestamp: now };

  const { userId, userName, sessionId } = getSessionInfo();

  const event: AuditLogCreate = {
    actor_id: userId,
    user_name: userName,
    session_id: sessionId,
    source: 'UI',
    action_type: 'page_exit',
    action: `exit ${pageTitle}`,
    component: component || pageTitle,
    route,
    page_title: pageTitle,
    duration_ms: durationMs,
    result: 'success',
  };

  queueEvent(event);
}

/**
 * Track a button click or user action
 */
export function trackClick(
  action: string,
  component: string,
  details?: {
    entityType?: string;
    entityId?: string;
    entityName?: string;
    params?: Record<string, unknown>;
  }
) {
  const { userId, userName, sessionId } = getSessionInfo();

  const event: AuditLogCreate = {
    actor_id: userId,
    user_name: userName,
    session_id: sessionId,
    source: 'UI',
    action_type: 'button_click',
    action,
    component,
    route: window.location.pathname,
    entity_type: details?.entityType,
    entity_id: details?.entityId,
    entity_name: details?.entityName,
    params: details?.params,
    result: 'success',
  };

  queueEvent(event);
}

/**
 * Flush all pending events immediately
 * Call this before page unload
 */
export function flushAnalytics() {
  return flushQueue();
}

/**
 * Configure analytics logging
 */
export function configureAnalytics(newConfig: Partial<AnalyticsConfig>) {
  Object.assign(config, newConfig);
}

// Flush on page unload
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    void flushQueue();
  });
}
