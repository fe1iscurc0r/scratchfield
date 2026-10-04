/**
 * sentinel 域 API（卷187：LoRaCanary 哨兵网格）。
 *
 * 对应 apiserver 的 `/sentinel/*` 端点：
 *   GET  /sentinel/nodes          在线节点 + 最后心跳
 *   GET  /sentinel/spectrum       时间窗内 RSSI 扫描数据
 *   GET  /sentinel/env            环境数据（温湿压/电池/GPS）
 *   GET  /sentinel/occupations    占用事件（同频点持续高 RSSI）
 *   POST /sentinel/scan_config    下发扫描配置
 */
import type { DomainShape } from './_context'

/** 节点在线状态。 */
export interface SentinelNode {
  node_id: string
  last_seen: number
  last_seen_iso: string
  fw: string | null
  frames: number
  online: boolean
  age_s: number
}

/** 单个频点扫描样本。 */
export interface SentinelScanBin {
  node_id: string
  ts: number
  freq_mhz: number
  rssi_dbm: number
  sf: number
}

/** 环境采样。 */
export interface SentinelEnvSample {
  node_id: string
  ts: number
  temp_c: number | null
  hum_pct: number | null
  pres_hpa: number | null
  bat_mv: number | null
  lat: number | null
  lon: number | null
}

/** 占用事件。 */
export interface SentinelOccupation {
  node_id: string
  freq_mhz: number
  start_ts: number
  end_ts: number
  duration_s: number
  peak_dbm: number
  mean_dbm: number
  n_samples: number
}

export const sentinelMethods = {
  /** 在线节点列表 + 最后心跳（心跳 >60s 由后端判 offline）。 */
  getSentinelNodes(): Promise<{
    count: number
    online: number
    offline_after_s: number
    nodes: SentinelNode[]
  }> {
    return this.instance.get('/sentinel/nodes')
  },

  /** 时间窗内 RSSI 扫描数据（`from`/`to` 为 Unix 秒）。 */
  getSentinelSpectrum(params: {
    from?: number
    to?: number
    node?: string
    limit?: number
  } = {}): Promise<{
    from: number
    to: number
    node: string | null
    count: number
    rows: SentinelScanBin[]
  }> {
    return this.instance.get('/sentinel/spectrum', { params })
  },

  /** 环境数据（默认最近 24 小时）。 */
  getSentinelEnv(params: { node?: string, hours?: number, limit?: number } = {}): Promise<{
    node: string | null
    hours: number
    count: number
    rows: SentinelEnvSample[]
  }> {
    return this.instance.get('/sentinel/env', { params })
  },

  /** 占用事件（新→旧）。 */
  getSentinelOccupations(params: { node?: string, hours?: number, limit?: number } = {}): Promise<{
    node: string | null
    hours: number
    count: number
    rows: SentinelOccupation[]
  }> {
    return this.instance.get('/sentinel/occupations', { params })
  },

  /** 下发扫描配置（节点 ack 后生效）。 */
  postSentinelScanConfig(payload: {
    node_id?: string | null
    freq_range?: [number, number]
    dwell_ms?: number
    sf_set?: number[]
    step_khz?: number
  }): Promise<{
    ok: boolean
    cmd_id: string
    target: string
    config: Record<string, unknown>
    delivered_to_bus: boolean
    note: string
  }> {
    return this.instance.post('/sentinel/scan_config', payload)
  },
} satisfies DomainShape
