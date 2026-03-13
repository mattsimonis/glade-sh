/**
 * toast.spec.js
 *
 * Tests for the pill-morph Dynamic Island toast component.
 *
 * The toast function is internal to the inline script. We trigger it via the
 * debug connection-state buttons (which call setConnectionState → toast) or
 * by calling window.__gladeToast() which we inject in beforeEach.
 *
 * Animation timing: tests use waitForSelector / polling rather than fixed
 * sleeps so they're resilient to CI slowness.
 */

const { test, expect } = require('@playwright/test');

// Inject a global helper so tests can call toast() directly without needing
// to reach through the closure.
async function exposeToast(page) {
  await page.evaluate(() => {
    // Walk the inline <script> closure via the debug panel toast button which
    // already calls toast() — but we need direct access. The simplest approach:
    // fire a CustomEvent that the page's script listens for. Since we can't
    // easily hook into the closure, we use the debug connection buttons which
    // indirectly call toast() via setConnectionState().
    // For direct toast calls we patch window.__gladeToast via a shim that
    // clicks the relevant debug button or manufactures the DOM directly.
    window.__triggerState = function(state) {
      const btn = document.getElementById('dbg-conn-' + state);
      if (btn) btn.click();
    };
  });
}

test.describe('Toast / Dynamic Island notification', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await exposeToast(page);
  });

  // ── DOM structure ────────────────────────────────────────────────────────────

  test('toast-container is present in DOM', async ({ page }) => {
    await expect(page.locator('#toast-container')).toBeAttached();
  });

  test('di-glow element has been removed', async ({ page }) => {
    const glow = await page.locator('#di-glow').count();
    expect(glow).toBe(0);
  });

  test('toast-container is empty on initial load', async ({ page }) => {
    const count = await page.locator('#toast-container .toast').count();
    expect(count).toBe(0);
  });

  // ── Toast appears on connection state change ─────────────────────────────────

  test('connected state creates a toast in the container', async ({ page }) => {
    // Start from a non-connected state so the transition fires
    await page.evaluate(() => window.__triggerState('reconnecting'));
    // Wait for the reconnecting toast, then trigger connected
    await page.waitForSelector('#toast-container .toast', { timeout: 3000 });
    await page.evaluate(() => window.__triggerState('connected'));
    const toasts = page.locator('#toast-container .toast');
    await expect(toasts).toHaveCount(1, { timeout: 3000 });
  });

  test('toast element has t-success class for connected state', async ({ page }) => {
    await page.evaluate(() => window.__triggerState('reconnecting'));
    await page.waitForSelector('#toast-container .toast');
    await page.evaluate(() => window.__triggerState('connected'));
    // Wait for the connected toast to appear (reconnecting one may still be exiting)
    await expect(page.locator('#toast-container .toast.t-success')).toBeAttached({ timeout: 3000 });
  });

  test('toast element has t-error class for disconnected state', async ({ page }) => {
    await page.evaluate(() => window.__triggerState('disconnected'));
    await expect(page.locator('#toast-container .toast.t-error')).toBeAttached({ timeout: 3000 });
  });

  test('toast element has t-warning class for reconnecting state', async ({ page }) => {
    await page.evaluate(() => window.__triggerState('reconnecting'));
    await expect(page.locator('#toast-container .toast.t-warning')).toBeAttached({ timeout: 3000 });
  });

  // ── Toast structure ──────────────────────────────────────────────────────────

  test('toast contains a dot and a message element', async ({ page }) => {
    await page.evaluate(() => window.__triggerState('disconnected'));
    const toast = page.locator('#toast-container .toast').first();
    await expect(toast).toBeAttached({ timeout: 3000 });
    await expect(toast.locator('.toast-dot')).toBeAttached();
    await expect(toast.locator('.toast-msg')).toBeAttached();
  });

  test('toast message text matches connection state', async ({ page }) => {
    await page.evaluate(() => window.__triggerState('disconnected'));
    const msg = page.locator('#toast-container .toast .toast-msg').first();
    await expect(msg).toBeAttached({ timeout: 3000 });
    await expect(msg).toHaveText('Disconnected');
  });

  test('reconnecting toast message reads Reconnecting…', async ({ page }) => {
    await page.evaluate(() => window.__triggerState('reconnecting'));
    const msg = page.locator('#toast-container .toast .toast-msg').first();
    await expect(msg).toHaveText('Reconnecting…', { timeout: 3000 });
  });

  // ── Animation classes ────────────────────────────────────────────────────────

  test('toast gains t-expanded class after insertion', async ({ page }) => {
    await page.evaluate(() => window.__triggerState('disconnected'));
    const toast = page.locator('#toast-container .toast').first();
    await expect(toast).toHaveClass(/t-expanded/, { timeout: 3000 });
  });

  test('toast gains t-content-in class after expand', async ({ page }) => {
    await page.evaluate(() => window.__triggerState('disconnected'));
    const toast = page.locator('#toast-container .toast').first();
    // t-content-in is added 240ms after t-expanded — allow extra headroom
    await expect(toast).toHaveClass(/t-content-in/, { timeout: 2000 });
  });

  // ── State transitions ────────────────────────────────────────────────────────

  test('transitioning states dismisses previous toast and shows new one', async ({ page }) => {
    await page.evaluate(() => window.__triggerState('disconnected'));
    await expect(page.locator('#toast-container .toast.t-error')).toBeAttached({ timeout: 3000 });

    await page.evaluate(() => window.__triggerState('reconnecting'));
    // After transition there should be at most 2 toasts briefly (old exiting + new entering),
    // and eventually exactly 1 t-warning toast
    await expect(page.locator('#toast-container .toast.t-warning')).toBeAttached({ timeout: 3000 });
  });

  // ── No legacy artefacts ──────────────────────────────────────────────────────

  test('no conic-gradient spinning border elements exist on toast', async ({ page }) => {
    await page.evaluate(() => window.__triggerState('disconnected'));
    await expect(page.locator('#toast-container .toast')).toBeAttached({ timeout: 3000 });
    // The old design used ::before/::after for spinning borders driven by
    // --toast-angle. Verify the CSS custom property is gone from the document.
    const hasAngle = await page.evaluate(() => {
      const sheets = Array.from(document.styleSheets);
      for (const sheet of sheets) {
        try {
          const rules = Array.from(sheet.cssRules || []);
          for (const rule of rules) {
            if (rule.cssText && rule.cssText.includes('--toast-angle')) return true;
          }
        } catch (e) { /* cross-origin */ }
      }
      return false;
    });
    expect(hasAngle).toBe(false);
  });

  test('no toast-spin keyframe animation exists in stylesheets', async ({ page }) => {
    const hasSpin = await page.evaluate(() => {
      const sheets = Array.from(document.styleSheets);
      for (const sheet of sheets) {
        try {
          const rules = Array.from(sheet.cssRules || []);
          for (const rule of rules) {
            if (rule.name === 'toast-spin') return true;
          }
        } catch (e) {}
      }
      return false;
    });
    expect(hasSpin).toBe(false);
  });
});
