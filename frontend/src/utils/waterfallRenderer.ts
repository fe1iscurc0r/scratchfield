/**
 * 瀑布图渲染器（Canvas 2D）
 *
 * 移植自 gbozo/no-sdr `client/src/engine/waterfall.ts`（MIT License），
 * 原始版权与许可见仓库 NOTICE 与上游 LICENSE。按本项目需要做了如下适配：
 *  1. 绘制目标改为共享画布的子矩形（originX/originY/w/h），不再独占整块 canvas；
 *  2. 滚动方向反转：最新一行画在底部（与 GQRX/SDR++ 及本面板时间轴「现在在下」一致）；
 *  3. 新增内部离屏表面 + renderAll(frames)：面板主画布每帧会整体重绘（轨迹层），
 *     若瀑布直接画在主画布上会被同帧的 clearRect 抹掉；改为渲染器自持离屏表面，
 *     缩放/换配色/resize 后由调用方用帧历史整幅重绘 —— 不再出现空白瀑布（修复
 *     旧实现离屏缓冲被重建即清空、且无历史数据源可恢复的缺陷）；
 *  4. 调色板改为 Uint8Array(256*3) 线性查找表，gamma 曲线语义与上游一致；
 *  5. blit() 把离屏表面贴到主画布子矩形，面板不再自己 clear 那块区域。
 */

export interface WaterfallView {
  /** 缩放视口，占整个频带的分数 [0,1] */
  zoomStart: number
  zoomEnd: number
}

export class WaterfallRenderer {
  private palette: Uint8Array<ArrayBufferLike> = new Uint8Array(256 * 3)
  private minDb = -120
  private maxDb = 0
  private gamma = 1
  private invert = false
  private zoomStart = 0
  private zoomEnd = 1
  private rowImg: ImageData | null = null
  private rowW = 0
  private lastDrawTime = 0
  /** 内部离屏表面：瀑布像素的唯一宿主，主画布每帧 blit 一次 */
  private surface: HTMLCanvasElement | null = null
  private sw = 0
  private sh = 0
  /** 瀑布不需要高帧率，节流到 ~30fps（上游同款） */
  private readonly minFrameInterval = 33

  constructor(
    palette: Uint8Array,
    minDb = -120,
    maxDb = 0,
  ) {
    this.setPalette(palette)
    this.minDb = minDb
    this.maxDb = maxDb
  }

  setPalette(palette: Uint8Array): void {
    if (palette.length >= 256 * 3)
      this.palette = palette
  }

  setRange(minDb: number, maxDb: number): void {
    this.minDb = minDb
    this.maxDb = maxDb
  }

  setGamma(gamma: number): void {
    this.gamma = Math.max(0.1, gamma)
  }

  setInvert(invert: boolean): void {
    this.invert = invert
  }

  setView(zoomStart: number, zoomEnd: number): void {
    this.zoomStart = Math.max(0, Math.min(zoomStart, zoomEnd - 0.01))
    this.zoomEnd = Math.min(1, Math.max(zoomEnd, this.zoomStart + 0.01))
  }

  private colorIndex(db: number): number {
    const range = this.maxDb - this.minDb
    if (range <= 0)
      return 0
    const norm = Math.max(0, Math.min(1, (db - this.minDb) / range))
    let idx = Math.round(norm ** this.gamma * 255)
    if (this.invert)
      idx = 255 - idx
    return Math.max(0, Math.min(255, idx))
  }

  /** 确保离屏表面尺寸正确；尺寸变化会清空内容，调用方随后应 renderAll()。 */
  private ensureSurface(w: number, h: number): HTMLCanvasElement | null {
    if (w < 1 || h < 1)
      return null
    if (!this.surface || this.sw !== w || this.sh !== h) {
      const c = document.createElement('canvas')
      c.width = w
      c.height = h
      this.surface = c
      this.sw = w
      this.sh = h
      this.rowImg = null
    }
    return this.surface
  }

  private surfCtx(): CanvasRenderingContext2D | null {
    return this.surface?.getContext('2d') ?? null
  }

  /**
   * 追加一行：现有内容整体上移 1px，最新一行画在底部。
   * 像素 → bin 映射带缩放感知：放大时线性插值，缩小时分块均值（上游同款）。
   */
  drawRow(w: number, h: number, db: Float32Array): void {
    const surface = this.ensureSurface(w, h)
    const ctx = this.surfCtx()
    if (!surface || !ctx || db.length === 0)
      return
    const now = performance.now()
    if (now - this.lastDrawTime < this.minFrameInterval)
      return
    this.lastDrawTime = now

    // 上移 1px（自拷贝）
    ctx.drawImage(surface, 0, 1, w, h - 1, 0, 0, w, h - 1)

    if (!this.rowImg || this.rowW !== w) {
      this.rowImg = ctx.createImageData(w, 1)
      this.rowW = w
    }
    this.paintRowInto(this.rowImg, db, w)
    ctx.putImageData(this.rowImg, 0, h - 1)
  }

  /** 把离屏表面贴到主画布（dpr 变换由调用方设定，目标为 CSS 像素坐标）。 */
  blit(ctx: CanvasRenderingContext2D, originX: number, originY: number): void {
    if (!this.surface)
      return
    ctx.drawImage(this.surface, originX, originY)
  }

  /** 从帧缓冲整幅重绘离屏表面（oldest first）。缩放/量程/配色变化或 resize 后调用。 */
  renderAll(w: number, h: number, frames: Float32Array[]): void {
    const surface = this.ensureSurface(w, h)
    const ctx = this.surfCtx()
    if (!surface || !ctx || frames.length === 0)
      return
    const img = ctx.createImageData(w, h)
    const px = img.data
    for (let row = 0; row < h; row++) {
      // 最新在底部
      const fi = frames.length - 1 - row
      const rowOff = row * w * 4
      if (fi < 0) {
        // 无数据的历史区域填底色（调色板 0 号），不再留透明
        for (let x = 0; x < w; x++) {
          const o = rowOff + x * 4
          px[o] = this.palette[0]!
          px[o + 1] = this.palette[1]!
          px[o + 2] = this.palette[2]!
          px[o + 3] = 255
        }
        continue
      }
      this.paintRowIntoAt(px, rowOff, frames[fi]!, w)
    }
    ctx.putImageData(img, 0, 0)
    this.lastDrawTime = performance.now() - this.minFrameInterval
  }

  private paintRowInto(img: ImageData, db: Float32Array, w: number): void {
    this.paintRowIntoAt(img.data, 0, db, w)
  }

  private paintRowIntoAt(px: Uint8ClampedArray, offset: number, db: Float32Array, w: number): void {
    const bins = db.length
    const viewStart = this.zoomStart * bins
    const viewEnd = this.zoomEnd * bins
    const viewBins = viewEnd - viewStart
    const binsPerPx = viewBins / w

    for (let x = 0; x < w; x++) {
      const binF = viewStart + (x / Math.max(1, w - 1)) * (viewBins - 1)
      let v: number
      if (binsPerPx <= 1) {
        const lo = Math.max(0, Math.min(bins - 1, Math.floor(binF)))
        const hi = Math.min(lo + 1, bins - 1)
        v = db[lo]! + (binF - lo) * (db[hi]! - db[lo]!)
      }
      else {
        const bs = Math.max(0, Math.floor(binF))
        const be = Math.min(bins, Math.floor(binF + binsPerPx))
        // 分块均值：瀑布比取峰值更平滑（上游注释同款取舍）
        let sum = db[bs]!
        for (let b = bs + 1; b < be; b++) sum += db[b]!
        v = sum / Math.max(1, be - bs)
      }
      const ci = this.colorIndex(v) * 3
      const o = offset + x * 4
      px[o] = this.palette[ci]!
      px[o + 1] = this.palette[ci + 1]!
      px[o + 2] = this.palette[ci + 2]!
      px[o + 3] = 255
    }
  }

  clear(w: number, h: number): void {
    const surface = this.ensureSurface(w, h)
    const ctx = this.surfCtx()
    if (!surface || !ctx)
      return
    ctx.fillStyle = `rgb(${this.palette[0]!},${this.palette[1]!},${this.palette[2]!})`
    ctx.fillRect(0, 0, w, h)
  }
}
