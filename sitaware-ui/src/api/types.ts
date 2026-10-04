// 前端类型定义，与后端 `sitaware/models.py` 序列化字段保持一致（WGS84）。

export type Severity = 'low' | 'medium' | 'high' | 'critical'
export type EventType = 'protest' | 'accident' | 'weather' | 'signal' | 'hazard' | 'custom'
export type Source = 'news' | 'rss' | 'ham_radio' | 'sensor' | 'user' | 'weather'

export interface Feature {
  type: 'Feature'
  id: string
  geometry: { type: string; coordinates: number[] | null }
  properties: Record<string, any>
}

export interface FeatureCollection {
  type: 'FeatureCollection'
  features: Feature[]
}

export interface AlertRule {
  id: string
  name: string
  bbox?: number[] | null
  center_lng?: number | null
  center_lat?: number | null
  radius_km?: number | null
  event_types: EventType[]
  min_severity: Severity
  enabled: boolean
  created_at?: string
}

export interface QueryResult {
  ok: boolean
  answer: string
  cited_events: Feature[]
  map_action: { type: string; center: number[]; zoom: number; label: string } | null
  llm_source: string | null
  risk_level?: string
}

export interface RoutePayload {
  ok: boolean
  primary: { geometry: any; distance_m: number | null; duration_s: number | null; source: string | null }
  alternatives: any[]
  risk_segments: any[]
  warnings: string[]
  start: number[]
  end: number[]
}

export interface Metrics {
  events_total: number
  events_today: number
  high_risk_today: number
  risk_level: string
  generated_at: number
}

export interface SummaryResult {
  ok: boolean
  summary: string
  summary_source: string
  risk_level: string
  counts: { total: number; by_type: Record<string, number>; by_severity: Record<string, number> }
  key_events: Feature[]
}
