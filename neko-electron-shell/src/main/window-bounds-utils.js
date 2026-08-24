const DEFAULT_WORK_AREA_FALLBACK_BOUNDS = {
  x: 0,
  y: 0,
  width: 1280,
  height: 720,
  minWidth: 720,
  minHeight: 560,
};

function getWorkAreaWindowInitialBounds(screen, anchorWin, options = {}) {
  const fallback = options.fallback || DEFAULT_WORK_AREA_FALLBACK_BOUNDS;
  const preferredMinWidth = Number.isFinite(options.minWidth) ? options.minWidth : DEFAULT_WORK_AREA_FALLBACK_BOUNDS.minWidth;
  const preferredMinHeight = Number.isFinite(options.minHeight) ? options.minHeight : DEFAULT_WORK_AREA_FALLBACK_BOUNDS.minHeight;
  try {
    const anchorBounds = anchorWin && typeof anchorWin.isDestroyed === 'function' && !anchorWin.isDestroyed()
      ? anchorWin.getBounds()
      : null;
    const display = anchorBounds
      ? screen.getDisplayMatching(anchorBounds)
      : screen.getPrimaryDisplay();
    const workArea = display && display.workArea ? display.workArea : screen.getPrimaryDisplay().workArea;
    const width = Math.max(1, workArea.width);
    const height = Math.max(1, workArea.height);
    return {
      x: workArea.x,
      y: workArea.y,
      width,
      height,
      minWidth: Math.min(Math.max(1, preferredMinWidth), width),
      minHeight: Math.min(Math.max(1, preferredMinHeight), height),
    };
  } catch (_) {
    return fallback;
  }
}

module.exports = {
  DEFAULT_WORK_AREA_FALLBACK_BOUNDS,
  getWorkAreaWindowInitialBounds,
};
