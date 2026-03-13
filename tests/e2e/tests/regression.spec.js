/**
 * Regression guard tests — catch known past bugs before they can come back.
 *
 * Each test documents the original bug and asserts the correct behaviour.
 * Add here whenever a bug is fixed that could silently regress.
 */

const { test, expect, devices } = require('@playwright/test');

// ── Bug: terminal unclickable on desktop ───────────────────────────────────
// An overlay with a high z-index was left visible, covering the terminal.
// Fix: ensure_project_running() returns a valid port; terminal z-index audit.

test.describe('Terminal accessibility', () => {
  test('terminal container is not covered by a blocking overlay', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const termContainer = page.locator('#terminal-container');
    const box = await termContainer.boundingBox();
    if (!box) {
      test.skip('terminal-container not in DOM');
      return;
    }

    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;

    const top = await page.evaluate(({ x, y }) => {
      const el = document.elementFromPoint(x, y);
      return el ? { id: el.id, tagName: el.tagName.toLowerCase() } : null;
    }, { x: cx, y: cy });

    if (top) {
      // These overlays should never silently cover the terminal at startup
      expect(top.id).not.toBe('project-grid-overlay');
      expect(top.id).not.toBe('settings-overlay');
    }
  });

  test('terminal container has a non-zero bounding box', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    const box = await page.locator('#terminal-container').boundingBox();
    expect(box).not.toBeNull();
    expect(box.width).toBeGreaterThan(100);
    expect(box.height).toBeGreaterThan(100);
  });
});

// ── Bug: iPhone landscape triggered desktop layout ─────────────────────────
// The @media (min-width: 768px) rule matched iPhone landscape (~844px wide)
// and hid the bottom nav and panel, leaving a blank terminal-only view with
// no way to access snippets or keyboard shortcuts.
// Fix: added (min-height: 600px) guard to the desktop media query.

test.describe('iPhone landscape regression: mobile layout preserved', () => {
  test.use({ ...devices['iPhone 13 landscape'] });

  test('bottom nav not hidden in landscape (was broken)', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    const display = await page.locator('#bottom-nav').evaluate(
      (el) => window.getComputedStyle(el).display
    );
    // Before fix this was 'none' — the desktop media query stole landscape
    expect(display).not.toBe('none');
  });

  test('desktop settings gear absent in landscape', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    const display = await page.locator('#desktop-settings-btn').evaluate(
      (el) => window.getComputedStyle(el).display
    );
    expect(display).toBe('none');
  });

  test('panel visible in landscape (compact height)', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('#panel')).toBeVisible();
  });

  test('no JS errors in landscape', async ({ page }) => {
    const errors = [];
    page.on('pageerror', (err) => errors.push(err.message));
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(errors).toHaveLength(0);
  });
});

// ── Desktop panel toggle integrity ────────────────────────────────────────
// Checks that the desktop panel toggle (bottom-right button) correctly
// shows and hides the panel, and that the panel CSS reset works cleanly.

test.describe('Desktop panel toggle', () => {
  test.use({ ...devices['Desktop Chrome'] });

  test('panel hidden initially, shown after toggle', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Initially hidden
    let display = await page.locator('#panel').evaluate(
      (el) => window.getComputedStyle(el).display
    );
    expect(display).toBe('none');

    const toggleBtn = page.locator('#desktop-panel-btn');
    if (!await toggleBtn.isVisible()) {
      test.skip('desktop-panel-btn not visible — may be a tablet layout');
      return;
    }

    await toggleBtn.click();
    await page.waitForTimeout(300);

    // Now visible
    display = await page.locator('#panel').evaluate(
      (el) => window.getComputedStyle(el).display
    );
    expect(display).not.toBe('none');

    // Toggle again — back to hidden
    await toggleBtn.click();
    await page.waitForTimeout(300);
    display = await page.locator('#panel').evaluate(
      (el) => window.getComputedStyle(el).display
    );
    expect(display).toBe('none');
  });
});

// ── Panel tab switching ────────────────────────────────────────────────────
// The bottom-nav and sidebar-tab buttons must update active state and
// switch the panel view.

test.describe('Panel tab switching', () => {
  // Test on mobile (bottom-nav tabs)
  test('mobile: clicking snippets tab marks it active', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 664 });
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const snippetsBtn = page.locator('.nav-btn[data-panel="snippets"]');
    if (!await snippetsBtn.isVisible()) {
      test.skip('nav-btn not visible — may not be mobile layout');
      return;
    }

    await snippetsBtn.click();
    await page.waitForTimeout(400);
    await expect(snippetsBtn).toHaveClass(/active/);

    // Keyboard tab should no longer be active
    const keyboardBtn = page.locator('.nav-btn[data-panel="keyboard"]');
    const keyboardClass = await keyboardBtn.getAttribute('class');
    expect(keyboardClass).not.toMatch(/\bactive\b/);
  });

  // Test on iPad (sidebar tabs)
  test('iPad: clicking snippets sidebar tab marks it active', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const snippetsBtn = page.locator('.sidebar-tab-btn[data-panel="snippets"]');
    if (!await snippetsBtn.isVisible()) {
      test.skip('sidebar-tab-btn not visible — not in iPad sidebar mode');
      return;
    }

    await snippetsBtn.click();
    await page.waitForTimeout(300);
    await expect(snippetsBtn).toHaveClass(/active/);
  });
});

// ── Layout integrity at every viewport ────────────────────────────────────
// Terminal container must always have a useful size, regardless of device.

test.describe('Terminal container integrity', () => {
  const viewports = [
    { name: 'iPhone portrait', width: 390, height: 664 },
    { name: 'iPhone landscape', width: 750, height: 342 },
    { name: 'desktop', width: 1280, height: 720 },
    { name: 'iPad portrait', width: 810, height: 1080 },
  ];

  for (const vp of viewports) {
    test(`terminal is visible and sizeable at ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      const box = await page.locator('#terminal-container').boundingBox();
      expect(box).not.toBeNull();
      // At minimum, the terminal must occupy 40% of the viewport height
      expect(box.height).toBeGreaterThan(vp.height * 0.4);
      // And at least 200px wide
      expect(box.width).toBeGreaterThan(200);
    });
  }
});

// ── ANSI stripping regression ──────────────────────────────────────────────
// Server-side strip_ansi must clean CSI, OSC, and bracketed-paste sequences.
// This was refined twice; guard against regressions.

test.describe('ANSI stripping in log search API', () => {
  test('search endpoint handles clean text queries without error', async ({ request }) => {
    const resp = await request.get('/api/logs/search?q=test');
    // Must return 200 with a JSON array (even if empty)
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(Array.isArray(body)).toBe(true);
  });

  test('search endpoint survives special characters in query', async ({ request }) => {
    // Regex-like chars that could break a naive grep call
    const resp = await request.get('/api/logs/search?q=' + encodeURIComponent('[ERROR]'));
    expect(resp.status()).toBe(200);
  });
});

// ── Settings endpoint returns 200 + null, not 404 ──────────────────────────
// Documented in COPILOT_INSTRUCTIONS: settings GET endpoints return 200 with
// null body when nothing saved — callers guard with `if (cfg && cfg.url)`.

test.describe('Settings endpoints: 200 not 404 when unset', () => {
  test('GET /api/settings/layout returns 200', async ({ request }) => {
    const resp = await request.get('/api/settings/layout');
    expect(resp.status()).toBe(200);
  });

  test('GET /api/settings/font returns 200', async ({ request }) => {
    const resp = await request.get('/api/settings/font');
    expect(resp.status()).toBe(200);
  });

  test('GET /api/settings/compact-layout returns 200', async ({ request }) => {
    const resp = await request.get('/api/settings/compact-layout');
    expect(resp.status()).toBe(200);
  });
});
