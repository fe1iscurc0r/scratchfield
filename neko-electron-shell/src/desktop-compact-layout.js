'use strict';

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function normalizeRect(raw) {
  if (!raw) return null;
  var left = Number(raw.left);
  var top = Number(raw.top);
  var width = Number(raw.width);
  var height = Number(raw.height);
  if (!Number.isFinite(left) || !Number.isFinite(top) || !Number.isFinite(width) || !Number.isFinite(height)) {
    return null;
  }
  if (width <= 0 || height <= 0) return null;
  return makeScreenRect(left, top, width, height);
}

function makeScreenRect(left, top, width, height) {
  var l = Math.round(Number(left) || 0);
  var t = Math.round(Number(top) || 0);
  var w = Math.max(1, Math.round(Number(width) || 1));
  var h = Math.max(1, Math.round(Number(height) || 1));
  return {
    left: l,
    top: t,
    width: w,
    height: h,
    right: l + w,
    bottom: t + h,
    centerX: l + w / 2,
    centerY: t + h / 2
  };
}

function unionScreenRects(rects) {
  var valid = (rects || []).map(normalizeRect).filter(Boolean);
  if (!valid.length) return null;
  var left = valid.reduce(function (min, rect) { return Math.min(min, rect.left); }, valid[0].left);
  var top = valid.reduce(function (min, rect) { return Math.min(min, rect.top); }, valid[0].top);
  var right = valid.reduce(function (max, rect) { return Math.max(max, rect.right); }, valid[0].right);
  var bottom = valid.reduce(function (max, rect) { return Math.max(max, rect.bottom); }, valid[0].bottom);
  return makeScreenRect(left, top, right - left, bottom - top);
}

function buildDesktopCompactHistoryPassiveReserveRect(options) {
  var opts = options || {};
  var surface = normalizeRect(opts.surfaceRect);
  if (!surface) return null;
  var measuredHistory = normalizeRect(opts.measuredHistoryRect);
  var cachedReserve = normalizeRect(opts.cachedReserveRect);
  var fallbackHeight = Math.round(Number(opts.fallbackHeight) || 0);
  var defaultGap = Math.max(0, Math.round(Number(opts.defaultGap) || 0));
  var gap = measuredHistory
    ? Math.max(0, Math.round(surface.top - measuredHistory.bottom))
    : defaultGap;
  // Tradeoff: keep the carrier reserve at the largest history panel height we
  // have seen instead of shrinking it to the currently mounted DOM. This leaves
  // more transparent BrowserWindow area than the visible UI strictly needs, but
  // it prevents native setBounds jumps when history opens, closes, or unmounts.
  // The reserve is carrier-only; hit/native rects stay based on real controls.
  var heightCandidates = [
    measuredHistory ? measuredHistory.height : 0,
    cachedReserve ? cachedReserve.height : 0,
    fallbackHeight
  ];
  var height = heightCandidates.reduce(function (max, value) {
    var next = Math.round(Number(value) || 0);
    return Number.isFinite(next) ? Math.max(max, next) : max;
  }, 0);
  if (height <= 0) return null;
  var workAreaTop = Number(opts.workArea && opts.workArea.y);
  if (Number.isFinite(workAreaTop)) {
    height = Math.min(height, Math.max(1, surface.top - gap - Math.round(workAreaTop)));
  }
  return makeScreenRect(surface.left, surface.top - gap - height, surface.width, height);
}

function convertPageRectToScreenRect(rect, windowBounds) {
  var normalized = normalizeRect(rect);
  if (!normalized || !windowBounds) return null;
  return makeScreenRect(
    Math.round(Number(windowBounds.x) || 0) + normalized.left,
    Math.round(Number(windowBounds.y) || 0) + normalized.top,
    normalized.width,
    normalized.height
  );
}

function translateScreenRect(rect, dx, dy) {
  var normalized = normalizeRect(rect);
  if (!normalized) return null;
  return makeScreenRect(normalized.left + dx, normalized.top + dy, normalized.width, normalized.height);
}

function shiftRectToTop(rect, top) {
  var normalized = normalizeRect(rect);
  if (!normalized) return null;
  return makeScreenRect(normalized.left, top, normalized.width, normalized.height);
}

function inferChoicePlacement(nativeRect, surfaceUnion) {
  var choice = normalizeRect(nativeRect);
  var surface = normalizeRect(surfaceUnion);
  if (!choice || !surface) return null;
  return choice.centerY < surface.centerY ? 'above' : 'below';
}

function rectFitsWorkArea(rect, area, pad) {
  var normalized = normalizeRect(rect);
  if (!normalized) return false;
  var areaX = Math.round(Number(area && area.x) || 0);
  var areaY = Math.round(Number(area && area.y) || 0);
  var areaWidth = Math.round(Number(area && area.width) || 0);
  var areaHeight = Math.round(Number(area && area.height) || 0);
  var inset = Math.max(0, Math.round(Number(pad) || 0));
  if (areaWidth > 0) {
    if (normalized.left < areaX + inset) return false;
    if (normalized.right > areaX + areaWidth - inset) return false;
  }
  if (areaHeight > 0) {
    if (normalized.top < areaY + inset) return false;
    if (normalized.bottom > areaY + areaHeight - inset) return false;
  }
  return true;
}

function clampScreenRectToWorkArea(rect, area, pad, options) {
  var normalized = normalizeRect(rect);
  if (!normalized) return null;
  var opts = options || {};
  var areaX = Math.round(Number(area && area.x) || 0);
  var areaY = Math.round(Number(area && area.y) || 0);
  var areaWidth = Math.round(Number(area && area.width) || 0);
  var areaHeight = Math.round(Number(area && area.height) || 0);
  var inset = Math.max(0, Math.round(Number(pad) || 0));
  var left = normalized.left;
  var top = normalized.top;
  if (areaWidth > 0) {
    var minLeft = areaX + inset;
    var maxLeft = areaX + Math.max(0, areaWidth - normalized.width - inset);
    left = clamp(left, minLeft, Math.max(minLeft, maxLeft));
  }
  if (areaHeight > 0) {
    var topInset = opts.allowTopEdge ? 0 : inset;
    var minTop = areaY + topInset;
    var maxTop = areaY + Math.max(0, areaHeight - normalized.height - inset);
    top = clamp(top, minTop, Math.max(minTop, maxTop));
  }
  return makeScreenRect(left, top, normalized.width, normalized.height);
}

function isDesktopCompactSurfaceAnchorKind(kind) {
  return kind === 'surfaceShell' || kind === 'capsule' || kind === 'input';
}

function isDesktopCompactBaseHitKind(kind) {
  return isDesktopCompactSurfaceAnchorKind(kind) || kind === 'inputControl';
}

function normalizeDesktopCompactSurfaceItems(surfaceItems, windowBounds) {
  if (!Array.isArray(surfaceItems)) return [];
  return surfaceItems.map(function (item) {
    if (!item) return null;
    var visualRect = item.visualRect == null ? null : convertPageRectToScreenRect(item.visualRect, windowBounds);
    var nativeRect = item.nativeRect == null ? null : convertPageRectToScreenRect(item.nativeRect, windowBounds);
    var interactive = item.interactive !== false;
    var hasHitRect = Object.prototype.hasOwnProperty.call(item, 'hitRect');
    var hitRect = null;
    if (interactive) {
      if (hasHitRect) {
        hitRect = item.hitRect == null ? null : convertPageRectToScreenRect(item.hitRect, windowBounds);
      } else {
        hitRect = nativeRect;
      }
    }
    if (!visualRect && !nativeRect && !hitRect) return null;
    return {
      id: item.id || item.kind || 'unknown',
      kind: item.kind || 'unknown',
      interactive: interactive,
      hitRegionKind: item.hitRegionKind || null,
      hasExplicitHitRect: hasHitRect,
      visualScreenRect: visualRect,
      nativeScreenRect: nativeRect,
      hitScreenRect: hitRect
    };
  }).filter(Boolean);
}

function classifyDesktopCompactItems(items) {
  var normalizedItems = Array.isArray(items) ? items.filter(Boolean) : [];
  var baseAnchorItems = normalizedItems.filter(function (item) {
    return isDesktopCompactSurfaceAnchorKind(item.kind);
  });
  var baseItems = normalizedItems.filter(function (item) {
    return isDesktopCompactBaseHitKind(item.kind);
  });
  var extraItems = normalizedItems.filter(function (item) {
    return !isDesktopCompactBaseHitKind(item.kind);
  });
  var boundsOnlyItems = normalizedItems.filter(function (item) {
    return item && item.nativeScreenRect && !item.hitScreenRect;
  });
  return {
    items: normalizedItems,
    baseAnchorItems: baseAnchorItems,
    baseItems: baseItems,
    extraItems: extraItems,
    boundsOnlyItems: boundsOnlyItems,
    baseAnchorVisualRects: baseAnchorItems.map(function (item) {
      return item.visualScreenRect || item.nativeScreenRect;
    }).filter(Boolean),
    baseAnchorNativeRects: baseAnchorItems.map(function (item) { return item.nativeScreenRect; }).filter(Boolean),
    baseNativeRects: baseItems.map(function (item) { return item.nativeScreenRect; }).filter(Boolean),
    baseHitRects: baseItems.map(function (item) { return item.hitScreenRect; }).filter(Boolean),
    extraVisualRects: extraItems.map(function (item) {
      return item.visualScreenRect || item.nativeScreenRect || item.hitScreenRect;
    }).filter(Boolean),
    extraNativeRects: extraItems.map(function (item) { return item.nativeScreenRect; }).filter(Boolean),
    extraHitRects: extraItems.map(function (item) { return item.hitScreenRect; }).filter(Boolean)
  };
}

function translateDesktopCompactItems(items, dx, dy) {
  return (Array.isArray(items) ? items : []).map(function (item) {
    if (!item) return null;
    return {
      id: item.id,
      kind: item.kind,
      interactive: item.interactive,
      hitRegionKind: item.hitRegionKind,
      hasExplicitHitRect: item.hasExplicitHitRect,
      visualScreenRect: translateScreenRect(item.visualScreenRect, dx, dy),
      nativeScreenRect: translateScreenRect(item.nativeScreenRect, dx, dy),
      hitScreenRect: translateScreenRect(item.hitScreenRect, dx, dy)
    };
  }).filter(Boolean);
}

function getDesktopCompactExtraHitPriority(item) {
  if (!item) return 50;
  if (item.kind === 'toolFan') return 10;
  if (item.kind === 'choice') return 20;
  return 50;
}

function sortDesktopCompactExtraHitItems(items) {
  return (Array.isArray(items) ? items : [])
    .map(function (item, index) {
      return { item: item, index: index };
    })
    .sort(function (left, right) {
      var priorityDelta = getDesktopCompactExtraHitPriority(left.item) - getDesktopCompactExtraHitPriority(right.item);
      return priorityDelta || (left.index - right.index);
    })
    .map(function (entry) {
      return entry.item;
    });
}

function isDesktopCompactStableToolFanItem(item) {
  if (!item || item.kind !== 'toolFan') return false;
  var id = String(item.id || '');
  return item.hitRegionKind === 'dragSurface'
    || id === 'toolFan:native'
    || id.indexOf('toolFan:native:') === 0;
}

function isDesktopCompactAvatarToolChoiceItem(item) {
  if (!item || item.kind !== 'toolFan') return false;
  return String(item.id || '').indexOf('toolFan:avatarToolChoice:') === 0;
}

function shouldIncludeDesktopCompactExtraHitItem(item) {
  if (!item || !item.hitScreenRect) return false;
  if (item.kind !== 'toolFan') return true;
  return isDesktopCompactStableToolFanItem(item)
    || isDesktopCompactAvatarToolChoiceItem(item);
}

function relocateChoiceItem(item, surfaceUnion, area, pad, preferredPlacement) {
  var nativeRect = item && item.nativeScreenRect;
  if (!nativeRect || item.kind !== 'choice' || !surfaceUnion) {
    return { item: item, compactChoicePlacement: null };
  }
  if (rectFitsWorkArea(nativeRect, area, pad)) {
    var currentPlacement = inferChoicePlacement(nativeRect, surfaceUnion);
    if (preferredPlacement === 'above' && currentPlacement === 'above') {
      var gap = 16;
      var below = shiftRectToTop(nativeRect, surfaceUnion.bottom + gap);
      return {
        item: item,
        compactChoicePlacement: rectFitsWorkArea(below, area, pad) ? null : 'above'
      };
    }
    return {
      item: item,
      compactChoicePlacement: null
    };
  }
  var areaY = Math.round(Number(area && area.y) || 0);
  var areaHeight = Math.round(Number(area && area.height) || 0);
  var areaBottom = areaY + areaHeight;
  var gap = 16;
  var above = shiftRectToTop(nativeRect, surfaceUnion.top - gap - nativeRect.height);
  var below = shiftRectToTop(nativeRect, surfaceUnion.bottom + gap);
  var nextNative = null;
  var placement = null;
  if (nativeRect.bottom > areaBottom && above && rectFitsWorkArea(above, area, pad)) {
    nextNative = above;
    placement = 'above';
  } else if (nativeRect.top < areaY && below && rectFitsWorkArea(below, area, pad)) {
    nextNative = below;
    placement = 'below';
  }
  if (!nextNative) return { item: item, compactChoicePlacement: null };
  var dx = nextNative.left - nativeRect.left;
  var dy = nextNative.top - nativeRect.top;
  return {
    item: {
      id: item.id,
      kind: item.kind,
      interactive: item.interactive,
      hitRegionKind: item.hitRegionKind,
      hasExplicitHitRect: item.hasExplicitHitRect,
      visualScreenRect: translateScreenRect(item.visualScreenRect, dx, dy),
      nativeScreenRect: nextNative,
      hitScreenRect: translateScreenRect(item.hitScreenRect, dx, dy)
    },
    compactChoicePlacement: placement
  };
}

function resolveDesktopCompactExtraItems(extraItems, surfaceUnion, area, pad, preferredChoicePlacement) {
  var compactChoicePlacement = null;
  var adjustedItems = (Array.isArray(extraItems) ? extraItems : []).map(function (item) {
    if (!item || (!item.nativeScreenRect && !item.hitScreenRect)) return null;
    if (!item.nativeScreenRect) return item;
    if (item.kind !== 'choice') return item;
    var relocated = relocateChoiceItem(item, surfaceUnion, area, pad, preferredChoicePlacement);
    if (relocated.compactChoicePlacement) {
      compactChoicePlacement = relocated.compactChoicePlacement;
    }
    return relocated.item;
  }).filter(Boolean);
  return {
    items: adjustedItems,
    compactChoicePlacement: compactChoicePlacement,
    nativeRects: adjustedItems
      .filter(function (item) { return item.kind !== 'toolFan'; })
      .map(function (item) { return item.nativeScreenRect; })
      .filter(Boolean),
    visualRects: adjustedItems.map(function (item) {
      return item.visualScreenRect || item.nativeScreenRect || item.hitScreenRect;
    }).filter(Boolean),
    hitRects: sortDesktopCompactExtraHitItems(adjustedItems.filter(shouldIncludeDesktopCompactExtraHitItem)).map(function (item) {
      return item.hitScreenRect;
    }).filter(Boolean)
  };
}

function isDesktopCompactHistoryPassthroughItem(item) {
  return !!(
    item
    && item.id === 'history:native'
    && item.kind === 'history'
    && item.nativeScreenRect
    && !item.hitScreenRect
  );
}

function isDesktopCompactHistoryResizeHitItem(item) {
  return !!(
    item
    && item.kind === 'history'
    && item.hitRegionKind === 'resize'
    && item.hitScreenRect
  );
}

function expandDesktopCompactHistoryResizeHoverRect(rect, historyBounds, options) {
  var resize = normalizeRect(rect);
  var bounds = normalizeRect(historyBounds);
  if (!resize || !bounds) return null;
  var opts = options || {};
  var padX = Math.max(0, Math.round(Number(opts.padX) || 0));
  var padTop = Math.max(0, Math.round(Number(opts.padTop) || 0));
  var padBottom = Math.max(0, Math.round(Number(opts.padBottom) || 0));
  var left = clamp(resize.left - padX, bounds.left, bounds.right);
  var top = clamp(resize.top - padTop, bounds.top, bounds.bottom);
  var right = clamp(resize.right + padX, bounds.left, bounds.right);
  var bottom = clamp(resize.bottom + padBottom, bounds.top, bounds.bottom);
  if (right <= left || bottom <= top) return null;
  return makeScreenRect(left, top, right - left, bottom - top);
}

function buildDesktopCompactHistoryResizeHoverRects(items, options) {
  var measuredItems = Array.isArray(items) ? items.filter(Boolean) : [];
  var historyBounds = unionScreenRects(measuredItems
    .filter(isDesktopCompactHistoryPassthroughItem)
    .map(function (item) { return item.nativeScreenRect; }));
  if (!historyBounds) return [];
  return measuredItems
    .filter(isDesktopCompactHistoryResizeHitItem)
    .map(function (item) {
      return expandDesktopCompactHistoryResizeHoverRect(item.hitScreenRect, historyBounds, options);
    })
    .filter(Boolean);
}

function sameDesktopCompactScreenRect(left, right) {
  var a = normalizeRect(left);
  var b = normalizeRect(right);
  return !!(
    a
    && b
    && a.left === b.left
    && a.top === b.top
    && a.width === b.width
    && a.height === b.height
  );
}

function containsDesktopCompactScreenRect(outer, inner) {
  var a = normalizeRect(outer);
  var b = normalizeRect(inner);
  return !!(
    a
    && b
    && a.left <= b.left
    && a.top <= b.top
    && a.right >= b.right
    && a.bottom >= b.bottom
  );
}

function isDesktopCompactHistoryHitOnlyItem(item) {
  return !!(
    item
    && item.kind === 'history'
    && item.hitScreenRect
    && !item.nativeScreenRect
  );
}

function buildDesktopCompactCarrierHitRects(hitRects, items) {
  var itemList = Array.isArray(items) ? items : [];
  var historyNativeRects = itemList
    .filter(function (item) { return item && item.kind === 'history' && item.nativeScreenRect; })
    .map(function (item) { return item.nativeScreenRect; })
    .filter(Boolean);
  var coveredHistoryHitOnlyRects = itemList
    .filter(isDesktopCompactHistoryHitOnlyItem)
    .filter(function (item) {
      return historyNativeRects.some(function (nativeRect) {
        return containsDesktopCompactScreenRect(nativeRect, item.hitScreenRect);
      });
    })
    .map(function (item) { return item.hitScreenRect; })
    .filter(Boolean);
  if (!coveredHistoryHitOnlyRects.length) return Array.isArray(hitRects) ? hitRects.filter(Boolean) : [];
  return (Array.isArray(hitRects) ? hitRects : [])
    .filter(Boolean)
    .filter(function (rect) {
      return !coveredHistoryHitOnlyRects.some(function (historyRect) {
        return sameDesktopCompactScreenRect(rect, historyRect);
      });
    });
}

function buildDesktopCompactToolFanReserveRect(baseAnchorItems, fallbackSurfaceRect, workArea) {
  var anchors = Array.isArray(baseAnchorItems) ? baseAnchorItems : [];
  var surfaceItem = anchors.find(function (item) {
    return item && item.kind === 'surfaceShell' && (item.visualScreenRect || item.nativeScreenRect);
  }) || anchors.find(function (item) {
    return item && item.kind === 'input' && (item.visualScreenRect || item.nativeScreenRect);
  }) || anchors.find(function (item) {
    return item && item.kind === 'capsule' && (item.visualScreenRect || item.nativeScreenRect);
  });
  var surfaceRect = normalizeRect(fallbackSurfaceRect)
    || normalizeRect(surfaceItem && (surfaceItem.visualScreenRect || surfaceItem.nativeScreenRect));
  if (!surfaceRect) return null;

  // Keep the desktop BrowserWindow bounds stable across opening/closing the
  // compact tool fan and across display/input state switches. The toggle center
  // is derived from the stable compact surface, not from input-only DOM.
  var toggleCenterRightInset = 31;
  var toggleCenterTopInset = 31;
  var wheelHoverRadius = 116;
  var wheelTopReserve = 140;
  var fanForwardReserve = 190;
  var centerX = surfaceRect.right - toggleCenterRightInset;
  var centerY = surfaceRect.top + toggleCenterTopInset;
  var reserve = makeScreenRect(
    centerX - wheelHoverRadius,
    centerY - wheelTopReserve,
    wheelHoverRadius + fanForwardReserve,
    wheelTopReserve + fanForwardReserve
  );
  var areaY = Math.round(Number(workArea && workArea.y) || 0);
  var areaHeight = Math.round(Number(workArea && workArea.height) || 0);
  if (areaHeight > 0) {
    var areaBottom = areaY + areaHeight;
    if (reserve.bottom > areaBottom) {
      reserve = makeScreenRect(reserve.left, Math.max(areaY, areaBottom - reserve.height), reserve.width, reserve.height);
    }
  }
  return reserve;
}

function buildDesktopCompactWindowBoundsForUnion(unionRect, area, pad) {
  var union = normalizeRect(unionRect);
  if (!union) return null;
  var inset = Math.max(0, Math.round(Number(pad) || 0));
  var areaX = Math.round(Number(area && area.x) || 0);
  var areaY = Math.round(Number(area && area.y) || 0);
  var areaWidth = Math.round(Number(area && area.width) || 0);
  var areaHeight = Math.round(Number(area && area.height) || 0);
  var x = union.left - inset;
  var y = union.top - inset;
  var right = union.right + inset;
  var bottom = union.bottom + inset;

  // Electron or the OS may clamp transparent BrowserWindows to the workArea.
  // Clip the carrier on every edge up front so taskbar/display-edge clamping
  // cannot feed back into the next compact relayout and move the base surface.
  if (areaWidth > 0) {
    var areaRight = areaX + areaWidth;
    x = Math.min(Math.max(areaX, x), areaRight - 1);
    right = Math.max(x + 1, Math.min(areaRight, right));
  }
  if (areaHeight > 0) {
    var areaBottom = areaY + areaHeight;
    y = Math.min(Math.max(areaY, y), areaBottom - 1);
    bottom = Math.max(y + 1, Math.min(areaBottom, bottom));
  }

  return {
    x: Math.round(x),
    y: Math.round(y),
    width: Math.max(1, Math.round(right - x)),
    height: Math.max(1, Math.round(bottom - y))
  };
}

function buildDesktopCompactTutorialFixedSurfaceRect(options) {
  var opts = options || {};
  var area = opts.workArea || {};
  var areaX = Math.round(Number(area.x) || 0);
  var areaY = Math.round(Number(area.y) || 0);
  var areaWidth = Math.round(Number(area.width) || 0);
  var areaHeight = Math.round(Number(area.height) || 0);
  var anchor = normalizeRect(opts.anchorSurface);
  var fallbackWidth = Math.round(Number(opts.fallbackWidth) || 400);
  var explicitWidth = Math.round(Number(opts.surfaceWidth) || 0);
  var preferredWidth = explicitWidth > 0 ? explicitWidth : (anchor ? anchor.width : fallbackWidth);
  var width = Math.max(1, Math.round(preferredWidth || fallbackWidth));
  var explicitHeight = Math.round(Number(opts.surfaceHeight) || 0);
  var preferredHeight = explicitHeight > 0 ? explicitHeight : (anchor ? anchor.height : 58);
  var height = Math.max(1, Math.round(preferredHeight || 58));
  var leftInset = clamp(Math.round(areaWidth > 0 ? areaWidth * 0.06 : 64), 24, 72);
  var rightInset = 24;
  var bottomInset = 24;
  if (areaWidth > 0) {
    width = Math.max(1, Math.min(width, areaWidth - leftInset - rightInset));
  }
  var minLeft = areaX + 24;
  var maxLeft = areaWidth > 0 ? Math.max(minLeft, areaX + areaWidth - width - rightInset) : areaX + leftInset;
  var targetTop = areaHeight > 0 ? areaY + Math.round(areaHeight * 0.62) : areaY + 420;
  var minTop = areaY + 24;
  var maxTop = areaHeight > 0 ? Math.max(minTop, areaY + areaHeight - height - bottomInset) : targetTop;
  return makeScreenRect(
    clamp(areaX + leftInset, minLeft, maxLeft),
    clamp(targetTop, minTop, maxTop),
    width,
    height
  );
}

function replaceDesktopCompactMeasuredBaseItemsWithSurface(items, surface, previousSurfaceFallback) {
  var fixedSurface = normalizeRect(surface);
  if (!fixedSurface) return Array.isArray(items) ? items.filter(Boolean) : [];
  var normalizedItems = Array.isArray(items) ? items.filter(Boolean) : [];
  var classified = classifyDesktopCompactItems(normalizedItems);
  var previousSurface = unionScreenRects(classified.baseAnchorVisualRects)
    || unionScreenRects(classified.baseAnchorNativeRects)
    || normalizeRect(previousSurfaceFallback);
  var dx = previousSurface ? Math.round(fixedSurface.left - previousSurface.left) : 0;
  var dy = previousSurface ? Math.round(fixedSurface.top - previousSurface.top) : 0;
  return normalizedItems.map(function (item) {
    if (!item) return null;
    if (!isDesktopCompactBaseHitKind(item.kind)) {
      return (dx || dy) ? translateDesktopCompactItems([item], dx, dy)[0] : item;
    }
    if (!isDesktopCompactSurfaceAnchorKind(item.kind)) {
      return (dx || dy) ? translateDesktopCompactItems([item], dx, dy)[0] : item;
    }
    return {
      id: item.id,
      kind: item.kind,
      interactive: item.interactive,
      hitRegionKind: item.hitRegionKind,
      hasExplicitHitRect: item.hasExplicitHitRect,
      visualScreenRect: isDesktopCompactSurfaceAnchorKind(item.kind) ? fixedSurface : item.visualScreenRect,
      nativeScreenRect: item.nativeScreenRect ? fixedSurface : null,
      hitScreenRect: item.hitScreenRect ? fixedSurface : null
    };
  }).filter(Boolean);
}

function buildDesktopCompactLayoutRects(options) {
  var opts = options || {};
  var area = opts.workArea || {};
  var pad = Math.max(0, Math.round(Number(opts.pad) || 0));
  var measuredItems = Array.isArray(opts.measuredItems) ? opts.measuredItems.filter(Boolean) : [];
  var preferredChoicePlacement = opts.compactChoicePlacement === 'above' || opts.compactChoicePlacement === 'below'
    ? opts.compactChoicePlacement
    : null;
  var classified = classifyDesktopCompactItems(measuredItems);
  var measuredSurface = normalizeRect(opts.measuredSurface);
  var actualSurfaceUnion = measuredSurface
    || unionScreenRects(classified.baseAnchorVisualRects)
    || unionScreenRects(classified.baseAnchorNativeRects);
  var hasActualSurfaceAnchor = !!actualSurfaceUnion;
  var storedSurfaceUnion = normalizeRect(opts.storedSurface);
  var desiredSurfaceUnion = storedSurfaceUnion
    || actualSurfaceUnion
    || normalizeRect(opts.fallbackSurface);
  var surfaceUnion = clampScreenRectToWorkArea(desiredSurfaceUnion, area, pad) || desiredSurfaceUnion;
  var surfaceDx = actualSurfaceUnion && surfaceUnion ? Math.round(surfaceUnion.left - actualSurfaceUnion.left) : 0;
  var surfaceDy = actualSurfaceUnion && surfaceUnion ? Math.round(surfaceUnion.top - actualSurfaceUnion.top) : 0;
  if (surfaceDx || surfaceDy) {
    measuredItems = translateDesktopCompactItems(measuredItems, surfaceDx, surfaceDy);
    classified = classifyDesktopCompactItems(measuredItems);
    if (!storedSurfaceUnion) {
      surfaceUnion = unionScreenRects(classified.baseAnchorVisualRects)
        || unionScreenRects(classified.baseAnchorNativeRects)
        || surfaceUnion;
    }
  }
  var adjustedExtra = hasActualSurfaceAnchor
    ? resolveDesktopCompactExtraItems(classified.extraItems, surfaceUnion, area, pad, preferredChoicePlacement)
    : {
      items: [],
      compactChoicePlacement: null,
      nativeRects: [],
      visualRects: [],
      hitRects: []
    };
  var toolFanReserveRect = buildDesktopCompactToolFanReserveRect(classified.baseAnchorItems, surfaceUnion, area);
  var historyPassiveReserveRect = normalizeRect(opts.historyPassiveReserveRect);
  var carrierReserveRects = [historyPassiveReserveRect].filter(Boolean);
  var hasMeasuredItems = measuredItems.length > 0;
  var baseNativeRects = classified.baseNativeRects.length
    ? classified.baseNativeRects
    : (!hasMeasuredItems && surfaceUnion ? [surfaceUnion] : []);
  if (storedSurfaceUnion && surfaceUnion && !hasMeasuredItems) {
    baseNativeRects = [surfaceUnion].concat(baseNativeRects);
  }
  var nativeRects = baseNativeRects
    .concat(adjustedExtra.nativeRects);
  if (!nativeRects.length && !hasMeasuredItems && surfaceUnion) nativeRects = [surfaceUnion];
  var hitRects = classified.baseHitRects.concat(adjustedExtra.hitRects);
  if (!hitRects.length && !hasMeasuredItems && surfaceUnion) hitRects = [surfaceUnion];
  var historyPassthroughRects = adjustedExtra.items
    .filter(isDesktopCompactHistoryPassthroughItem)
    .map(function (item) { return item.nativeScreenRect; })
    .filter(Boolean);
  return {
    surfaceUnion: surfaceUnion,
    surfaceDx: surfaceDx,
    surfaceDy: surfaceDy,
    baseItems: classified.baseItems,
    baseAnchorItems: classified.baseAnchorItems,
    extraItems: adjustedExtra.items,
    boundsOnlyItems: classified.boundsOnlyItems,
    baseAnchorVisualRects: classified.baseAnchorVisualRects,
    baseNativeRects: classified.baseNativeRects,
    baseHitRects: classified.baseHitRects,
    extraVisualRects: adjustedExtra.visualRects,
    extraNativeRects: adjustedExtra.nativeRects,
    extraHitRects: adjustedExtra.hitRects,
    carrierReserveRects: carrierReserveRects,
    toolFanReserveRect: toolFanReserveRect,
    hasMeasuredItems: hasMeasuredItems,
    nativeRects: nativeRects,
    hitRects: hitRects,
    historyPassthroughRects: historyPassthroughRects,
    compactChoicePlacement: adjustedExtra.compactChoicePlacement
  };
}

module.exports = {
  normalizeRect: normalizeRect,
  makeScreenRect: makeScreenRect,
  unionScreenRects: unionScreenRects,
  buildDesktopCompactHistoryPassiveReserveRect: buildDesktopCompactHistoryPassiveReserveRect,
  convertPageRectToScreenRect: convertPageRectToScreenRect,
  translateScreenRect: translateScreenRect,
  rectFitsWorkArea: rectFitsWorkArea,
  clampScreenRectToWorkArea: clampScreenRectToWorkArea,
  isDesktopCompactSurfaceAnchorKind: isDesktopCompactSurfaceAnchorKind,
  isDesktopCompactBaseHitKind: isDesktopCompactBaseHitKind,
  normalizeDesktopCompactSurfaceItems: normalizeDesktopCompactSurfaceItems,
  classifyDesktopCompactItems: classifyDesktopCompactItems,
  translateDesktopCompactItems: translateDesktopCompactItems,
  sortDesktopCompactExtraHitItems: sortDesktopCompactExtraHitItems,
  isDesktopCompactStableToolFanItem: isDesktopCompactStableToolFanItem,
  shouldIncludeDesktopCompactExtraHitItem: shouldIncludeDesktopCompactExtraHitItem,
  resolveDesktopCompactExtraItems: resolveDesktopCompactExtraItems,
  isDesktopCompactHistoryPassthroughItem: isDesktopCompactHistoryPassthroughItem,
  isDesktopCompactHistoryResizeHitItem: isDesktopCompactHistoryResizeHitItem,
  isDesktopCompactHistoryHitOnlyItem: isDesktopCompactHistoryHitOnlyItem,
  expandDesktopCompactHistoryResizeHoverRect: expandDesktopCompactHistoryResizeHoverRect,
  buildDesktopCompactHistoryResizeHoverRects: buildDesktopCompactHistoryResizeHoverRects,
  buildDesktopCompactCarrierHitRects: buildDesktopCompactCarrierHitRects,
  buildDesktopCompactWindowBoundsForUnion: buildDesktopCompactWindowBoundsForUnion,
  buildDesktopCompactTutorialFixedSurfaceRect: buildDesktopCompactTutorialFixedSurfaceRect,
  replaceDesktopCompactMeasuredBaseItemsWithSurface: replaceDesktopCompactMeasuredBaseItemsWithSurface,
  buildDesktopCompactLayoutRects: buildDesktopCompactLayoutRects
};
