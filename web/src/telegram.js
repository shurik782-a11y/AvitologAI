/** Telegram Mini App bootstrap: expand, fullscreen, safe-area CSS vars. */

const HEADER = "#12161f";
const BG = "#0e1118";

function px(n) {
  const v = Number(n);
  return Number.isFinite(v) && v > 0 ? `${v}px` : "0px";
}

function applyInsets(tg) {
  const root = document.documentElement;
  const safe = tg?.safeAreaInset || {};
  const content = tg?.contentSafeAreaInset || {};

  root.style.setProperty("--tg-safe-top", px(safe.top));
  root.style.setProperty("--tg-safe-bottom", px(safe.bottom));
  root.style.setProperty("--tg-safe-left", px(safe.left));
  root.style.setProperty("--tg-safe-right", px(safe.right));

  root.style.setProperty("--tg-content-safe-top", px(content.top));
  root.style.setProperty("--tg-content-safe-bottom", px(content.bottom));
  root.style.setProperty("--tg-content-safe-left", px(content.left));
  root.style.setProperty("--tg-content-safe-right", px(content.right));
}

function applyViewportHeight(tg) {
  const root = document.documentElement;
  const vv = window.visualViewport;
  let h = 0;
  if (vv && vv.height > 0) {
    h = vv.height;
  } else if (tg?.viewportStableHeight > 0) {
    h = tg.viewportStableHeight;
  } else if (tg?.viewportHeight > 0) {
    h = tg.viewportHeight;
  } else {
    h = window.innerHeight;
  }
  root.style.setProperty("--tg-viewport-height", `${Math.round(h)}px`);
}

function bindViewport(tg) {
  const refresh = () => {
    applyInsets(tg);
    applyViewportHeight(tg);
  };
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
}

export function initTelegram() {
  const tg = window.Telegram?.WebApp;
  if (!tg) {
    document.documentElement.style.setProperty("--tg-viewport-height", `${window.innerHeight}px`);
    window.addEventListener("resize", () => {
      document.documentElement.style.setProperty(
        "--tg-viewport-height",
        `${window.visualViewport?.height || window.innerHeight}px`
      );
    });
    window.visualViewport?.addEventListener("resize", () => {
      document.documentElement.style.setProperty(
        "--tg-viewport-height",
        `${window.visualViewport.height}px`
      );
    });
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
  try {
    tg.requestFullscreen?.();
  } catch {
    /* Bot API < 8 or user denied */
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

  document.documentElement.dataset.theme = tg.colorScheme || "dark";
  bindViewport(tg);
  return tg;
}
