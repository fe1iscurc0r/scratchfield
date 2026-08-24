import type { Router } from 'vue-router'
import { watch } from 'vue'
import API from '@/api/core'
import { backendConnected } from '@/utils/config'

interface TelemetryEvent {
  event: string
  props?: Record<string, any>
  source?: string
  traceId?: string
  sessionId?: string
  agentId?: string
}

const pendingEvents: TelemetryEvent[] = []
let flushing = false
let appLaunchSent = false
let telemetryInitialized = false
const TELEMETRY_QUEUE_LIMIT = 100
const appStartedAt = performance.now()

async function flushPending() {
  if (flushing || !backendConnected.value || pendingEvents.length === 0)
    return
  flushing = true
  try {
    while (pendingEvents.length > 0 && backendConnected.value) {
      const next = pendingEvents[0]!
      try {
        await API.trackTelemetry(next)
        pendingEvents.shift()
      }
      catch {
        break
      }
    }
  }
  finally {
    flushing = false
  }
}

export function trackTelemetry(event: string, props: Record<string, any> = {}, context: Omit<TelemetryEvent, 'event' | 'props'> = {}) {
  pendingEvents.push({
    event,
    props,
    source: context.source || 'frontend',
    traceId: context.traceId,
    sessionId: context.sessionId,
    agentId: context.agentId,
  })
  if (pendingEvents.length > TELEMETRY_QUEUE_LIMIT)
    pendingEvents.shift()
  void flushPending()
}

export function initTelemetry(router: Router) {
  if (telemetryInitialized)
    return
  telemetryInitialized = true

  watch(backendConnected, (connected) => {
    if (!connected)
      return
    if (!appLaunchSent) {
      appLaunchSent = true
      trackTelemetry('app_launch', {
        startupMs: Math.round(performance.now() - appStartedAt),
        route: router.currentRoute.value.fullPath,
        windowWidth: window.innerWidth,
        windowHeight: window.innerHeight,
        screenWidth: window.screen.width,
        screenHeight: window.screen.height,
      })
    }
    trackTelemetry('backend_connected', {
      route: router.currentRoute.value.fullPath,
    })
    void flushPending()
  }, { immediate: true })

  router.afterEach((to, from) => {
    trackTelemetry('route_view', {
      route: to.fullPath,
      routeName: typeof to.name === 'string' ? to.name : '',
      from: from.fullPath,
    })
  })
}
