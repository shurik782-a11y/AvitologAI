/** Telegram Mini App: expand + safe frame CSS vars (under Close / edges / home bar). */

const HEADER = "#12161f";
const BG = "#0e1118";
const FLOOR_TOP = 52;
const FLOOR_BOTTOM = 20;
const FLOOR_SIDE = 4;

function num(n) {
  const v = Number(n);
  return Number.isFinite(v) && v > 0 ? v : 0;
}

function px(n) {
  return `${Math.max(0, Math.round(n))}px`;
}

function applyFrame(tg) {
  const root = document.documentElement;
  const inTg = Boolean(tg);
  const safe = tg?.safeAreaInset || {};
  const content = tg?.contentSafeAreaInset || {};

  const floorTop = inTg ? FLOOR_TOP : 0;
  const floorBottom = inTg ? FLOOR_BOTTOM : 0;
  const floorSide = inTg ? FLOOR_SIDE : 0;

  const top = Math.max(num(content.top), num(safe.top), floorTop);
  const bottom = Math.max(num(content.bottom), num(safe.bottom), floorBottom);
  const left = Math.max(num(content.left), num(safe.left), floorSide);
  const right = Math.max(num(content.right), num(safe.right), floorSide);

  root.style.setProperty("--tg-frame-top", px(top));
  root.style.setProperty("--tg-frame-bottom", px(bottom));
  root.style.setProperty("--tg-frame-left", px(left));
  root.style.setProperty("--tg-frame-right", px(right));

  // Legacy vars (used by older rules) — keep in sync
  root.style.setProperty("--tg-safe-top", px(num(safe.top)));
  root.style.setProperty("--tg-safe-bottom", px(num(safe.bottom)));
  root.style.setProperty("--tg-safe-left", px(num(safe.left)));
  root.style.setProperty("--tg-safe-right", px(num(safe.right)));
  root.style.setProperty("--tg-content-safe-top", px(num(content.top)));
  root.style.setProperty("--tg-content-safe-bottom", px(num(content.bottom)));
  root.style.setProperty("--tg-content-safe-left", px(num(content.left)));
  root.style.setProperty("--tg-content-safe-right", px(num(content.right)));

  applyViewportHeight(tg);
}

function applyViewportHeight(tg) {
  const root = document.documentElement;
  const vv = window.visualViewport;
  const stable =
    num(tg?.viewportStableHeight) || num(tg?.viewportHeight) || window.innerHeight || 0;
  let h = stable;
  // Only shrink for keyboard — ignore tiny visualViewport jitter
  if (vv && vv.height > 0 && stable - vv.height > 40) {
    h = vv.height;
  }
  if (h > 0) {
    root.style.setProperty("--tg-viewport-height", px(h));
  }
}

function bindViewport(tg) {
  const refresh = () => applyFrame(tg);
  refresh();
  try {
    tg?.onEvent?.("viewportChanged", refresh);
    tg?.onEvent?.("safeAreaChanged", refresh);
    tg?.onEvent?.("contentSafeAreaChanged", refresh);
    tg?.onEvent?.("fullscreenChanged", refresh);
  } catch {
    /* older clients */
  }
  window.visualViewport?.addEventListener("resize", refresh);
  window.visualViewport?.addEventListener("scroll", refresh);
  window.addEventListener("resize", refresh);
  // TG often sends insets after expand settles
  setTimeout(refresh, 100);
  setTimeout(refresh, 300);
  setTimeout(refresh, 800);
}

export function initTelegram() {
  const tg = window.Telegram?.WebApp;
  if (!tg) {
    document.documentElement.style.setProperty("--tg-frame-top", "0px");
    document.documentElement.style.setProperty("--tg-frame-bottom", "0px");
    document.documentElement.style.setProperty("--tg-frame-left", "0px");
    document.documentElement.style.setProperty("--tg-frame-right", "0px");
    document.documentElement.style.setProperty(
      "--tg-viewport-height",
      `${window.innerHeight}px`
    );
    const refresh = () => {
      const h = window.visualViewport?.height || window.innerHeight;
      document.documentElement.style.setProperty("--tg-viewport-height", `${Math.round(h)}px`);
    };
    window.addEventListener("resize", refresh);
    window.visualViewport?.addEventListener("resize", refresh);
    return null;
  }

  try {
    tg.ready();
  } catch {
    /* ignore */
  }
  try {
    tg.expand();
  } catch {
    /* ignore */
  }
  // Do NOT requestFullscreen — TG Close/controls overlay the WebView harder
  try {
    tg.exitFullscreen?.();
  } catch {
    /* ignore */
  }
  try {
    tg.setHeaderColor?.(HEADER);
    tg.setBackgroundColor?.(BG);
  } catch {
    /* ignore */
  }
  try {
    tg.disableVerticalSwipes?.();
  } catch {
    /* ignore */
  }
  try {
    tg.requestContentSafeArea?.();
    tg.requestSafeArea?.();
  } catch {
    /* ignore */
  }

  document.documentElement.dataset.theme = tg.colorScheme || "dark";
  bindViewport(tg);
  return tg;
}
