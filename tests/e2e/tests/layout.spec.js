/**
 * Layout tests — verify the correct UI layout is applied at each viewport.
 *
 * Breakpoint strategy:
 *   Mobile portrait  (default)            — bottom nav + slide-up panel
 *   iPhone landscape (max-height: 500px)  — compact mobile (nav/panel still visible)
 *   Desktop          (≥768px + ≥600px + pointer:fine) — panel/nav hidden, desktop controls
 *   iPad/tablet      (≥768px + ≥600px + pointer:coarse) — Termius sidebar
 *
 * Note: iPad sidebar tests rely on `pointer: coarse`, which Playwright correctly
 * emulates when `isMobile: true` is set (iPad (gen 7) device). Run these on the
 * 'iPad portrait' or 'iPad landscape' projects for correct results.
 */

const { test, expect, devices } = require('@playwright/test');

async function computedDisplay(page, selector) {
  return page.locator(selector).evaluate(
    (el) => window.getComputedStyle(el).display
  );
}

// ── iPhone portrait ────────────────────────────────────────────────────────

test.describe('iPhone portrait: mobile layout', () => {
  test.use({ ...devices['iPhone 13'] });

  test('bottom nav is visible', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('#bottom-nav')).toBeVisible();
  });

  test('desktop controls are hidden', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(await computedDisplay(page, '#desktop-settings-btn')).toBe('none');
    expect(await computedDisplay(page, '#desktop-panel-btn')).toBe('none');
  });

  test('sidebar tabs are hidden (mobile uses bottom nav)', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(await computedDisplay(page, '#panel-sidebar-tabs')).toBe('none');
  });

  test('panel is present and above bottom nav', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    const panel = page.locator('#panel');
    const nav = page.locator('#bottom-nav');
    const panelBox = await panel.boundingBox();
    const navBox = await nav.boundingBox();
    if (panelBox && navBox) {
      // Panel sits above the nav bar
      expect(panelBox.y + panelBox.height).toBeLessThanOrEqual(navBox.y + 4);
    }
  });

  test('no JS errors on load', async ({ page }) => {
    const errors = [];
    page.on('pageerror', (err) => errors.push(err.message));
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(errors).toHaveLength(0);
  });
});

// ── iPhone landscape ───────────────────────────────────────────────────────
// Key regression: used to trigger desktop mode (display:none on bottom-nav).

test.describe('iPhone landscape: compact mobile layout', () => {
  test.use({ ...devices['iPhone 13 landscape'] });

  test('bottom nav is visible (not hidden by desktop rule)', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('#bottom-nav')).toBeVisible();
  });

  test('desktop settings gear is hidden', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(await computedDisplay(page, '#desktop-settings-btn')).toBe('none');
  });

  test('desktop panel button is hidden', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(await computedDisplay(page, '#desktop-panel-btn')).toBe('none');
  });

  test('panel is visible (compact height)', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('#panel')).toBeVisible();
  });

  test('sidebar tabs are hidden (not in iPad mode)', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(await computedDisplay(page, '#panel-sidebar-tabs')).toBe('none');
  });

  test('no JS errors on load', async ({ page }) => {
    const errors = [];
    page.on('pageerror', (err) => errors.push(err.message));
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(errors).toHaveLength(0);
  });
});

// ── Desktop ────────────────────────────────────────────────────────────────

test.describe('Desktop: layout preserved', () => {
  test.use({ ...devices['Desktop Chrome'] });

  test('bottom nav hidden on desktop', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(await computedDisplay(page, '#bottom-nav')).toBe('none');
  });

  test('panel hidden by default on desktop', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(await computedDisplay(page, '#panel')).toBe('none');
  });

  test('desktop settings gear is visible', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('#desktop-settings-btn')).toBeVisible();
  });

  test('sidebar tabs hidden (desktop uses gear not sidebar)', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(await computedDisplay(page, '#panel-sidebar-tabs')).toBe('none');
  });

  test('terminal container fills most of the viewport', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    const bbox = await page.locator('#terminal-container').boundingBox();
    expect(bbox).not.toBeNull();
    expect(bbox.height).toBeGreaterThan(720 * 0.7);
    expect(bbox.width).toBeGreaterThan(1280 * 0.9);
  });

  test('no JS errors on load', async ({ page }) => {
    const errors = [];
    page.on('pageerror', (err) => errors.push(err.message));
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(errors).toHaveLength(0);
  });
});

// ── iPad portrait ──────────────────────────────────────────────────────────
// Requires pointer:coarse — use iPad device (isMobile:true emulates coarse pointer).

test.describe('iPad portrait: Termius sidebar layout', () => {
  test.use({ ...devices['iPad (gen 7)'] });

  test('panel sidebar tabs are visible', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('#panel-sidebar-tabs')).toBeVisible();
  });

  test('bottom nav is hidden', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(await computedDisplay(page, '#bottom-nav')).toBe('none');
  });

  test('panel is visible as a sidebar', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('#panel')).toBeVisible();
  });

  test('app is laid out as a row (panel left, terminal right)', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    const flexDir = await page.locator('#app').evaluate(
      (el) => window.getComputedStyle(el).flexDirection
    );
    expect(flexDir).toBe('row');
  });

  test('panel sidebar is left of terminal container', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    const panelBox = await page.locator('#panel').boundingBox();
    const termBox = await page.locator('#terminal-container').boundingBox();
    if (panelBox && termBox) {
      expect(panelBox.x).toBeLessThan(termBox.x);
    }
  });

  test('keyboard panel view is visible by default', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('#pv-keyboard')).toBeVisible();
  });

  test('desktop controls are hidden on iPad', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(await computedDisplay(page, '#desktop-panel-btn')).toBe('none');
  });

  test('no JS errors on load', async ({ page }) => {
    const errors = [];
    page.on('pageerror', (err) => errors.push(err.message));
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(errors).toHaveLength(0);
  });
});

// ── iPad landscape ─────────────────────────────────────────────────────────

test.describe('iPad landscape: sidebar layout with project access', () => {
  test.use({ ...devices['iPad (gen 7) landscape'] });

  test('panel sidebar tabs are visible', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('#panel-sidebar-tabs')).toBeVisible();
  });

  test('bottom nav is hidden', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(await computedDisplay(page, '#bottom-nav')).toBe('none');
  });

  test('panel is visible as a sidebar', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('#panel')).toBeVisible();
  });

  test('terminal has substantial width in landscape', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    const termBox = await page.locator('#terminal-container').boundingBox();
    if (termBox) {
      // iPad (gen 7) landscape is 1080px wide; terminal should be > 600px after sidebar
      expect(termBox.width).toBeGreaterThan(600);
    }
  });

  test('no JS errors on load', async ({ page }) => {
    const errors = [];
    page.on('pageerror', (err) => errors.push(err.message));
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(errors).toHaveLength(0);
  });
});
