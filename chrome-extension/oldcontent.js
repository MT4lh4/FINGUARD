// FinGuard AI - Content Script (Trendyol / Hepsiburada / Amazon TR)
// Sepete ekle tıklamalarını: çoklu seçici + metin yedeği ile yakalar

console.log("[FinGuard] Impulse Guard yüklendi:", location.hostname);

/** @typedef {{ cartSelectors: string[], nameSelectors: string[], priceSelectors: string[] }} SiteCfg */

/** @type {Record<string, SiteCfg>} */
const SITE_CONFIG = {
  "trendyol.com": {
    cartSelectors: [
      ".add-to-basket",
      "button.add-to-basket",
      "[data-testid='addToBasket']",
      "[data-testid='primary-add-to-basket']",
      "[data-testid='add-to-basket-button']",
      "button[data-tracker='addToBasket']",
      "button[aria-label*='Sepete' i]",
      "a[aria-label*='Sepete' i]",
      "[class*='add-to-basket' i]",
      "[class*='addToBasket' i]",
    ],
    nameSelectors: [
      "h1.pr-new-br span",
      "h1.pr-new-br",
      ".pr-new-br h1 span",
      "[data-testid='product-name']",
      "h1.product-name",
      "span.product-name",
    ],
    priceSelectors: [
      ".prc-dsc",
      "[data-testid='price-current-price']",
      ".prc-box-org .prc-dsc",
      "[id='price-current-price']",
      "span[data-testid='price-current-price']",
    ],
  },
  "hepsiburada.com": {
    cartSelectors: [
      "#addToCart",
      "button#addToCart",
      "[data-test-id='addToCart']",
      "button[data-test-id='addToCart']",
      "[data-test-id='add-to-cart']",
      "button[aria-label*='Sepete' i]",
      "button[aria-label*='SEPETE' i]",
      "[class*='addToCart' i]",
      "[class*='AddToCart' i]",
    ],
    nameSelectors: [
      "h1#product-name",
      "h1[data-test-id='product-name']",
      "[data-test-id='product-name']",
      "h1.product-title",
      "h1",
    ],
    priceSelectors: [
      "[data-test-id='price-current-price']",
      "[data-test-id='product-price']",
      ".product-price",
      "#product-price",
      "span[data-test-id='price-current-price']",
    ],
  },
  "amazon.com.tr": {
    cartSelectors: [
      "#add-to-cart-button",
      "#submit.add-to-cart",
      "input#add-to-cart-button",
      "button[name='submit.add-to-cart']",
      "#rcx-subscribe-submit-button",
    ],
    nameSelectors: ["#productTitle", "#title"],
    priceSelectors: [
      ".a-price .a-offscreen",
      ".a-price-whole",
      "span.a-price.a-text-price .a-offscreen",
    ],
  },
};

const DECISION_STYLES = {
  "HAYIR_BUTCE_YOK": {
    accent: "#dc2626", accentLight: "#fca5a5",
    svg: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#dc2626" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
    label: "BÜTÇE YOK",
  },
  "KESİNLİKLE ALMA": {
    accent: "#ef4444", accentLight: "#fca5a5",
    svg: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
    label: "KESİNLİKLE ALMA",
  },
  BEKLE: {
    accent: "#f59e0b", accentLight: "#fcd34d",
    svg: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
    label: "BEKLE",
  },
  "ALTERNATİFLERE BAK": {
    accent: "#06b6d4", accentLight: "#67e8f9",
    svg: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#06b6d4" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
    label: "ALTERNATİFLERE BAK",
  },
  AL: {
    accent: "#10b981", accentLight: "#6ee7b7",
    svg: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
    label: "ALIYORUM! 🎉",
  },
  LOADING: {
    accent: "#818cf8", accentLight: "#c7d2fe",
    svg: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#818cf8" stroke-width="2.5" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>`,
    label: "ANALİZ EDİLİYOR",
  },
  ERROR: {
    accent: "#64748b", accentLight: "#94a3b8",
    svg: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2.5" stroke-linecap="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    label: "HATA",
  },
};


function detectSite(hostname) {
  const h = hostname.toLowerCase();
  if (h.includes("trendyol.com")) return "trendyol.com";
  if (h.includes("hepsiburada.com")) return "hepsiburada.com";
  if (h.includes("amazon.com.tr")) return "amazon.com.tr";
  return "";
}

function firstText(selectors) {
  for (const sel of selectors) {
    try {
      const el = document.querySelector(sel);
      const t = el?.innerText?.trim();
      if (t && t.length > 1 && t.length < 500) return t;
    } catch (_) {
      /* invalid selector */
    }
  }
  const og = document.querySelector('meta[property="og:title"]')?.content?.trim();
  if (og) return og.slice(0, 400);
  const t = document.title?.trim();
  if (t) return t.replace(/\s*\|\s*Trendyol.*$/i, "").replace(/\s*\|\s*Hepsiburada.*$/i, "").slice(0, 400);
  return "Bilinmeyen Ürün";
}

function parsePrice(raw) {
  if (raw == null) return 0;
  let s = String(raw)
    .replace(/\s/g, "")
    .replace(/TL|₺|TRY/gi, "");
  s = s.replace(/[^\d.,]/g, "");
  if (!s) return 0;
  const hasComma = s.includes(",");
  const hasDot = s.includes(".");
  if (hasComma && hasDot) {
    if (s.lastIndexOf(",") > s.lastIndexOf(".")) s = s.replace(/\./g, "").replace(",", ".");
    else s = s.replace(/,/g, "");
  } else if (hasComma) {
    const parts = s.split(",");
    if (parts.length === 2 && parts[1].length <= 2)
      s = parts[0].replace(/\./g, "") + "." + parts[1];
    else s = s.replace(/,/g, "");
  } else if (hasDot) {
    const parts = s.split(".");
    if (parts.length === 2 && parts[1].length === 3 && /^\d{3}$/.test(parts[1]) && parts[0].length <= 3)
      s = parts[0] + parts[1];
  }
  const n = parseFloat(s);
  return Number.isFinite(n) ? n : 0;
}

function firstPrice(selectors) {
  for (const sel of selectors) {
    try {
      const el = document.querySelector(sel);
      const raw = el?.innerText ?? el?.textContent;
      const p = parsePrice(raw);
      if (p > 0) return p;
    } catch (_) {}
  }
  return 0;
}

/**
 * Sepete ekle tıklamasını tanır (Shadow DOM için event.composedPath kullanır).
 * @param {EventTarget|null} target
 * @param {Event} event
 * @param {string} siteKey
 */
function resolveCartClick(target, event, siteKey) {
  if (!target) return null;
  const cfg = SITE_CONFIG[siteKey];
  if (!cfg) return null;

  /** @type {Element[]} */
  const roots = [];
  if (event && typeof event.composedPath === "function") {
    try {
      for (const n of event.composedPath()) {
        if (n instanceof Element) roots.push(n);
      }
    } catch (_) {}
  }
  if (!roots.length && target instanceof Element) {
    for (let n = target; n; n = n.parentElement) roots.push(n);
  }

  const seen = new Set();
  for (const start of roots) {
    let node = start;
    for (let depth = 0; depth < 18 && node; depth++, node = node.parentElement) {
      if (seen.has(node)) continue;
      seen.add(node);

      for (const sel of cfg.cartSelectors) {
        try {
          if (node.matches(sel) && isVisible(node)) return node;
        } catch (_) {
          /* geçersiz seçici */
        }
      }

      const tag = node.tagName?.toLowerCase();
      if (!["button", "a"].includes(tag) && node.getAttribute("role") !== "button") continue;
      const text = (node.innerText || node.textContent || "").replace(/\s+/g, " ").trim();
      if (text && /sepete\s*ekle/i.test(text) && text.length < 120 && isVisible(node)) return node;
    }
  }
  return null;
}

function isVisible(el) {
  if (!(el instanceof Element)) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return false;
  const st = window.getComputedStyle(el);
  return st.visibility !== "hidden" && st.display !== "none" && st.opacity !== "0";
}

function normalizeDecision(d) {
  if (d == null) return "BEKLE";
  const u = String(d).toUpperCase().replace(/\s+/g, " ").trim();
  if (u.includes("KESIN") && u.includes("ALMA")) return "KESİNLİKLE ALMA";
  if (u === "AL" || u.includes("SATIN AL")) return "AL";
  if (u.includes("ALTERNATIF")) return "ALTERNATİFLERE BAK";
  if (u.includes("BEKLE")) return "BEKLE";
  if (DECISION_STYLES[d]) return d;
  return "BEKLE";
}

const currentSite = detectSite(window.location.hostname);

if (currentSite) {
  document.body.addEventListener(
    "click",
    function (e) {
      const cartEl = resolveCartClick(e.target, e, currentSite);
      if (!cartEl) return;

      e.preventDefault();
      e.stopPropagation();

      const cfg = SITE_CONFIG[currentSite];
      const productName = firstText(cfg.nameSelectors);
      const price = firstPrice(cfg.priceSelectors);

      console.log("[FinGuard] Sepete ekle:", productName, price, "TL @", currentSite);

      showFinguardOverlay("Alışveriş alışkanlıkların analiz ediliyor...", true);

      chrome.runtime.sendMessage({
        action: "analyze_impulse",
        product: {
          name: productName,
          price,
          site: currentSite,
          url: location.href,
        },
      });
    },
    true
  );
}

chrome.runtime.onMessage.addListener(function (request) {
  if (request.action === "show_decision") {
    const raw = request.data?.decision;
    const decision = normalizeDecision(raw);
    showFinguardOverlay(
      request.data.message,
      false,
      decision,
      request.data.category,
      request.data.budget_status,
      request.data.alternatives
    );
  } else if (request.action === "show_error") {
    showFinguardOverlay("Bir hata oluştu: " + (request.error || "Bilinmeyen"), false, "ERROR");
  }
});

function showFinguardOverlay(message, isLoading, decision = null, category = null, budget = null, alternatives = null) {
  let overlay = document.getElementById("finguard-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "finguard-overlay";
    document.body.appendChild(overlay);
  }

  const styleKey = isLoading ? "LOADING" : (DECISION_STYLES[decision] ? decision : "ERROR");
  const style = DECISION_STYLES[styleKey];

  // Budget bar
  let budgetHtml = "";
  if (budget && !isLoading && typeof budget === "object") {
    const lim = Number(budget.aylik_limit) || 1;
    const har = Number(budget.harcanan) || 0;
    const kal = Number(budget.kalan);
    const pct = Math.min(100, Math.round((har / lim) * 100));
    const barColor = pct >= 100 ? '#ef4444' : pct >= 80 ? '#f59e0b' : '#10b981';
    budgetHtml = `
      <div style="margin:14px 0;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:12px;padding:14px;">
        <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
          <span style="font-size:12px;font-weight:600;color:rgba(255,255,255,0.7);">${category || 'Kategori'} B\u00fct\u00e7esi</span>
          <span style="font-size:12px;font-weight:800;color:${barColor};">${pct}%</span>
        </div>
        <div style="height:5px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden;">
          <div style="height:100%;width:${pct}%;background:${barColor};border-radius:3px;transition:width .8s ease;"></div>
        </div>
        <div style="display:flex;justify-content:space-between;margin-top:8px;font-size:11px;color:rgba(255,255,255,0.5);">
          <span>Harcanan: <b style="color:rgba(255,255,255,0.8)">${har.toLocaleString('tr-TR')} \u20BA</b></span>
          <span>Kalan: <b style="color:rgba(255,255,255,0.8)">${Number.isFinite(kal) ? kal.toLocaleString('tr-TR') : '\u2014'} \u20BA</b></span>
        </div>
      </div>`;
  }

  const svgIcon = style.svg || '';
  const spinStyle = isLoading ? 'animation:fg-spin 1s linear infinite;transform-origin:center;' : '';

  overlay.innerHTML = `
    <style>
      #finguard-overlay {
        position:fixed;inset:0;z-index:2147483647;
        background:rgba(0,0,0,0.75);backdrop-filter:blur(8px);
        display:flex;align-items:center;justify-content:center;
        animation:fg-fade .25s ease;
      }
      @keyframes fg-fade { from{opacity:0} to{opacity:1} }
      @keyframes fg-spin  { to{transform:rotate(360deg)} }
      @keyframes fg-up    { from{transform:translateY(20px);opacity:0} to{transform:translateY(0);opacity:1} }
      .fg-glass {
        background:rgba(15,15,20,0.92);
        border:1px solid ${style.accent}44;
        border-top:2px solid ${style.accent};
        border-radius:20px;
        padding:24px;
        width:360px;
        max-width:calc(100vw - 40px);
        box-shadow:0 0 40px ${style.accent}22, 0 20px 60px rgba(0,0,0,0.6);
        animation:fg-up .3s ease;
        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
        color:#fff;
      }
    </style>
    <div class="fg-glass">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <div style="display:flex;align-items:center;gap:10px;">
          <div style="font-size:20px;">\u{1F6E1}\uFE0F</div>
          <div>
            <div style="font-size:14px;font-weight:800;letter-spacing:.3px;">FinGuard AI</div>
            <div style="font-size:10px;color:rgba(255,255,255,0.4);">Finansal Vicdan\u0131n</div>
          </div>
        </div>
        ${!isLoading ? `<button id="fg-close" style="background:rgba(255,255,255,0.08);border:none;color:rgba(255,255,255,0.5);width:28px;height:28px;border-radius:50%;cursor:pointer;font-size:14px;display:flex;align-items:center;justify-content:center;" aria-label="Kapat">&times;</button>` : ''}
      </div>

      <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;">
        <div style="${spinStyle}flex-shrink:0;">${svgIcon}</div>
        <div style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:${style.accent};">${style.label}</div>
      </div>

      <div style="font-size:13px;line-height:1.65;color:rgba(255,255,255,0.75);">${String(message || '').replace(/\n/g, '<br>')}</div>

      ${budgetHtml}

      ${(alternatives && !isLoading) ? `
        <div style="margin:14px 0;background:rgba(6,182,212,0.06);border:1px solid rgba(6,182,212,0.15);border-radius:12px;padding:14px;">
          <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#67e8f9;margin-bottom:8px;display:flex;align-items:center;gap:6px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#67e8f9" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            Alternatif & Fiyat Bilgisi
          </div>
          <div style="font-size:12px;line-height:1.7;color:rgba(255,255,255,0.65);">
            ${String(alternatives).split('\\n').filter(l => l.trim()).map(line =>
              '<div style="padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.04);">' + line.replace(/^-\s*/, '• ') + '</div>'
            ).join('')}
          </div>
        </div>` : ''}

      ${!isLoading ? `
        <div style="display:flex;gap:8px;margin-top:18px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.08);">
          ${decision !== 'AL' ? `<button id="fg-force-buy" style="flex:1;padding:10px;border-radius:10px;background:rgba(239,68,68,0.12);border:1px solid rgba(239,68,68,0.3);color:#f87171;font-size:13px;font-weight:600;cursor:pointer;">Yine de Al</button>` : ''}
          <button id="fg-okay" style="flex:2;padding:10px;border-radius:10px;background:${style.accent}22;border:1px solid ${style.accent}55;color:${style.accent};font-size:13px;font-weight:700;cursor:pointer;">
            ${decision === 'AL' ? 'Harika, Al\u0131yorum! \uD83C\uDF89' : 'Hakl\u0131s\u0131n, Vaz\u0131ge\u00E7tim'}
          </button>
        </div>` : ''}
    </div>`;

  overlay.style.display = "flex";

  if (!isLoading) {
    const closeBtn = document.getElementById("fg-close");
    if (closeBtn) closeBtn.onclick = closeOverlay;
    const okBtn = document.getElementById("fg-okay");
    if (okBtn) okBtn.onclick = closeOverlay;
    const forceBtn = document.getElementById("fg-force-buy");
    if (forceBtn) forceBtn.onclick = () => { closeOverlay(); alert('\uD83D\uDCDD Uyard\u0131rmalar\u0131m\u0131 reddediyorsun \u2014 b\u00FCt\u00E7ene not edildi!'); };
  }

  overlay.addEventListener('click', ev => { if (ev.target === overlay) closeOverlay(); }, { once: true });
}

function closeOverlay() {
  const el = document.getElementById("finguard-overlay");
  if (el) el.style.display = "none";
}
