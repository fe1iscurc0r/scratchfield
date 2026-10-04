/**
 * 频谱轨迹渲染器（Canvas 2D）
 *
 * 移植自 gbozo/no-sdr `client/src/engine/spectrum.ts`（MIT License），
 * 原始版权与许可见仓库 NOTICE 与上游 LICENSE。按本项目需要做了如下适配：
 *  1. 绘制目标改为共享画布的子矩形（originX/originY/w/h），不再独占整块 canvas；
 *  2. 网格与 dB 刻度改由本项目的 spectrumAxis.ts 自适应阶梯绘制（上游固定 10/20 dB
 *     步进，在矮画布上同样会重叠），本渲染器只负责轨迹/填充/峰值保持/噪声底线；
 *  3. 冻结改由面板层统一门控（同时冻结瀑布），渲染器内不再单独持有冻结帧；
 *  4. 像素级 dB 缓冲对外返回，供面板做光标读数与峰值标注，避免二次映射。
 */

export interface TraceView {
  /** 缩放视口，占整个频带的分数 [0,1] */
  zoomStart: number
  zoomEnd: number
}

/** 画布像素 x → 视口内连续 bin 坐标（缩放感知，供读数/点击复用）。 */
export function xToBinF(x: number, w: number, bins: number, zoomStart: number, zoomEnd: number): number {
  const viewStart = zoomStart * bins
  const viewEnd = zoomEnd * bins
  const viewBins = viewEnd - viewStart
  return viewStart + (x / Math.max(1, w - 1)) * (viewBins - 1)
}

/** 连续 bin 坐标 → dB（放大线性插值 / 缩小取块内峰值，与上游一致）。 */
export function binFToDb(binF: number, binsPerPx: number, data: Float32Array): number {
  const bins = data.length
  if (binsPerPx <= 1) {
    const lo = Math.max(0, Math.min(bins - 1, Math.floor(binF)))
    const hi = Math.min(lo + 1, bins - 1)
    return data[lo]! + (binF - lo) * (data[hi]! - data[lo]!)
  }
  const bs = Math.max(0, Math.floor(binF))
  const be = Math.min(bins, Math.floor(binF + binsPerPx))
  let v = data[bs]!
  for (let b = bs + 1; b < be; b++) {
    if (data[b]! > v)
      v = data[b]!
  }
  return v
}

export class SpectrumTraceRenderer {
  private minDb = -120
  private maxDb = 0
  private accentColor = '#4f8cff'
  private fillColor = 'rgba(79,140,255,0.12)'
  private signalFillColor = 'rgba(79,140,255,0.25)'
  private zoomStart = 0
  private zoomEnd = 1

  /** 客户端显示平滑（EMA）。0=关闭，0.4=中，0.7=慢（上游语义） */
  private smoothingAlpha = 0
  private smoothedDb: Float32Array | null = null

  private peakHoldEnabled = false
  private peakDb: Float32Array | null = null
  private peakDecayDbPerFrame = 0.4

  private signalFillEnabled = false

  /** 噪声底线：滚动窗口逐 bin 最小值（信号峰不会抬高估计，上游同款思路） */
  private noiseFloorEnabled = false
  private noiseFloorWindow: Float32Array[] | null = null
  private noiseFloorWindowPos = 0
  private noiseFloorBins: Float32Array | null = null
  private readonly NOISE_FLOOR_MAX_FRAMES = 150
  private readonly NOISE_FLOOR_MAX_BYTES = 4 * 1024 * 1024
  private noiseFloorWindowSize = 150

  private pixelDbBuf: Float32Array | null = null

  get isZoomed(): boolean {
    return this.zoomStart > 0 || this.zoomEnd < 1
  }

  getZoom(): [number, number] {
    return [this.zoomStart, this.zoomEnd]
  }

  setRange(minDb: number, maxDb: number): void {
    this.minDb = minDb
    this.maxDb = maxDb
  }

  setAccentColor(color: string): void {
    this.accentColor = color
    let r = 79
    let g = 140
    let b = 255
    const hex6 = color.match(/^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i)
    const hex3 = color.match(/^#([0-9a-f])([0-9a-f])([0-9a-f])$/i)
    if (hex6) {
      r = Number.parseInt(hex6[1]!, 16)
      g = Number.parseInt(hex6[2]!, 16)
      b = Number.parseInt(hex6[3]!, 16)
    }
    else if (hex3) {
      r = Number.parseInt(hex3[1]! + hex3[1]!, 16)
      g = Number.parseInt(hex3[2]! + hex3[2]!, 16)
      b = Number.parseInt(hex3[3]! + hex3[3]!, 16)
    }
    this.fillColor = `rgba(${r},${g},${b},0.12)`
    this.signalFillColor = `rgba(${r},${g},${b},0.25)`
  }

  setSmoothing(alpha: number): void {
    this.smoothingAlpha = Math.max(0, Math.min(0.95, alpha))
    this.smoothedDb = null
  }

  setPeakHold(enabled: boolean): void {
    this.peakHoldEnabled = enabled
    if (!enabled)
      this.peakDb = null
  }

  resetPeak(): void {
    this.peakDb = null
  }

  setPeakDecay(dbPerFrame: number): void {
    this.peakDecayDbPerFrame = Math.max(0.05, dbPerFrame)
  }

  setSignalFill(enabled: boolean): void {
    this.signalFillEnabled = enabled
  }

  setNoiseFloor(enabled: boolean): void {
    this.noiseFloorEnabled = enabled
    if (!enabled) {
      this.noiseFloorWindow = null
      this.noiseFloorBins = null
      this.noiseFloorWindowPos = 0
    }
  }

  setView(zoomStart: number, zoomEnd: number): void {
    this.zoomStart = Math.max(0, Math.min(zoomStart, zoomEnd - 0.01))
    this.zoomEnd = Math.min(1, Math.max(zoomEnd, this.zoomStart + 0.01))
    // 峰值缓冲按像素索引，缩放后失效；噪声底按 bin 索引，可跨缩放保留（上游同款）
    this.peakDb = null
    this.pixelDbBuf = null
  }

  /**
   * 绘制一帧轨迹，返回像素级 dB 数组（长度 = w，供光标读数复用）。
   * 就绪数据不足时返回 null。
   */
  draw(
    ctx: CanvasRenderingContext2D,
    originX: number,
    originY: number,
    w: number,
    h: number,
    fftData: Float32Array,
  ): Float32Array | null {
    if (fftData.length === 0 || w < 1 || h < 1)
      return null

    // 客户端显示平滑（EMA）
    let data = fftData
    if (this.smoothingAlpha > 0) {
      if (!this.smoothedDb || this.smoothedDb.length !== fftData.length) {
        this.smoothedDb = new Float32Array(fftData)
      }
      else {
        const a = this.smoothingAlpha
        const b = 1 - a
        for (let i = 0; i < fftData.length; i++)
          this.smoothedDb[i] = a * this.smoothedDb[i]! + b * fftData[i]!
        data = this.smoothedDb
      }
    }
    else {
      this.smoothedDb = null
    }

    const bins = data.length
    const range = this.maxDb - this.minDb
    if (range <= 0)
      return null

    const viewStart = this.zoomStart * bins
    const viewEnd = this.zoomEnd * bins
    const viewBins = viewEnd - viewStart
    const binsPerPx = viewBins / w

    // 预分配的像素级 dB 缓冲，避免每帧分配（上游同款）
    if (!this.pixelDbBuf || this.pixelDbBuf.length !== w)
      this.pixelDbBuf = new Float32Array(w)
    const pixelDb = this.pixelDbBuf
    for (let x = 0; x < w; x++)
      pixelDb[x] = binFToDb(xToBinF(x, w, bins, this.zoomStart, this.zoomEnd), binsPerPx, data)

    const yFor = (db: number): number => {
      const norm = Math.max(0, Math.min(1, (db - this.minDb) / range))
      return originY + h - norm * h
    }

    // 曲线下方淡填充
    ctx.beginPath()
    ctx.moveTo(originX, originY + h)
    for (let x = 0; x < w; x++) ctx.lineTo(originX + x, yFor(pixelDb[x]!))
    ctx.lineTo(originX + w, originY + h)
    ctx.closePath()
    ctx.fillStyle = this.fillColor
    ctx.fill()

    // 信号柱状填充（可选）：逐像素从底填到峰，信号「向上发光」
    if (this.signalFillEnabled) {
      ctx.fillStyle = this.signalFillColor
      for (let x = 0; x < w; x++) {
        const y = yFor(pixelDb[x]!)
        ctx.fillRect(originX + x, y, 1, originY + h - y)
      }
    }

    // 轨迹线
    ctx.beginPath()
    for (let x = 0; x < w; x++) {
      const y = yFor(pixelDb[x]!)
      if (x === 0)
        ctx.moveTo(originX, y)
      else ctx.lineTo(originX + x, y)
    }
    ctx.strokeStyle = this.accentColor
    ctx.lineWidth = 1.5
    ctx.stroke()

    // 峰值保持：捕获新高 + 缓慢衰减（上游 0.4dB/帧 @30fps ≈ 12dB/s）
    if (!this.peakDb || this.peakDb.length !== w) {
      this.peakDb = new Float32Array(w).fill(this.minDb)
    }
    for (let x = 0; x < w; x++) {
      if (pixelDb[x]! > this.peakDb[x]!) {
        this.peakDb[x] = pixelDb[x]!
      }
      else {
        this.peakDb[x] = Math.max(this.minDb, this.peakDb[x]! - this.peakDecayDbPerFrame)
      }
    }
    if (this.peakHoldEnabled) {
      ctx.beginPath()
      for (let x = 0; x < w; x++) {
        const y = yFor(this.peakDb[x]!)
        if (x === 0)
          ctx.moveTo(originX, y)
        else ctx.lineTo(originX + x, y)
      }
      ctx.strokeStyle = this.accentColor
      ctx.globalAlpha = 0.55
      ctx.lineWidth = 1
      ctx.stroke()
      ctx.globalAlpha = 1
    }

    // 噪声底线：滚动窗口逐 bin 最小值，虚线
    if (this.noiseFloorEnabled)
      this.drawNoiseFloor(ctx, originX, originY, w, h, data, bins, viewStart, viewBins, binsPerPx, yFor)

    return pixelDb
  }

  private drawNoiseFloor(
    ctx: CanvasRenderingContext2D,
    originX: number,
    originY: number,
    w: number,
    h: number,
    data: Float32Array,
    bins: number,
    viewStart: number,
    viewBins: number,
    binsPerPx: number,
    yFor: (db: number) => number,
  ): void {
    if (!this.noiseFloorWindow || this.noiseFloorWindow[0]?.length !== bins) {
      this.noiseFloorWindowSize = Math.max(10, Math.min(
        this.NOISE_FLOOR_MAX_FRAMES,
        Math.floor(this.NOISE_FLOOR_MAX_BYTES / (bins * 4)),
      ))
      // 注意：不能用 .fill(new Float32Array(bins))——fill 会让所有槽位共享同一数组
      // eslint-disable-next-line e18e/prefer-array-fill -- TypedArray 填充必须用映射回调，fill 会共享引用
      const win = Array.from({ length: this.noiseFloorWindowSize }, () => new Float32Array(bins))
      for (const slot of win)
        slot.set(data)
      this.noiseFloorWindow = win
      this.noiseFloorWindowPos = 0
      this.noiseFloorBins = new Float32Array(bins)
    }
    const win = this.noiseFloorWindow!
    win[this.noiseFloorWindowPos]!.set(data)
    this.noiseFloorWindowPos = (this.noiseFloorWindowPos + 1) % this.noiseFloorWindowSize

    // 每 3 帧重算一次窗口内逐 bin 最小值，控制 CPU（上游同款）
    if (this.noiseFloorWindowPos % 3 === 0) {
      const floor = this.noiseFloorBins!
      for (let b = 0; b < bins; b++) {
        let mn = win[0]![b]!
        for (let f = 1; f < win.length; f++) {
          if (win[f]![b]! < mn)
            mn = win[f]![b]!
        }
        floor[b] = mn
      }
    }

    const floor = this.noiseFloorBins!
    ctx.beginPath()
    for (let x = 0; x < w; x++) {
      const binF = xToBinF(x, w, bins, this.zoomStart, this.zoomEnd)
      let floorDb: number
      if (binsPerPx <= 1) {
        const lo = Math.max(0, Math.min(bins - 1, Math.floor(binF)))
        const hi = Math.min(lo + 1, bins - 1)
        floorDb = floor[lo]! + (binF - lo) * (floor[hi]! - floor[lo]!)
      }
      else {
        const bs = Math.max(0, Math.floor(binF))
        const be = Math.min(bins, Math.floor(binF + binsPerPx))
        floorDb = floor[bs]!
        for (let b = bs + 1; b < be; b++) {
          if (floor[b]! < floorDb)
            floorDb = floor[b]!
        }
      }
      const y = yFor(floorDb)
      if (x === 0)
        ctx.moveTo(originX, y)
      else ctx.lineTo(originX + x, y)
    }
    ctx.setLineDash([4, 3])
    ctx.strokeStyle = '#a855f7'
    ctx.globalAlpha = 0.7
    ctx.lineWidth = 1
    ctx.stroke()
    ctx.setLineDash([])
    ctx.globalAlpha = 1
  }

  clear(ctx: CanvasRenderingContext2D, originX: number, originY: number, w: number, h: number): void {
    ctx.clearRect(originX, originY, w, h)
  }
}
