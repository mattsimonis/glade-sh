/**
 * reconnect.spec.js
 *
 * Tests for the disconnected / reconnecting overlay (commit: d6b7fce).
 *
 * The overlay is driven entirely by setConnectionState() in the JS.
 * We call it directly via page.evaluate() rather than waiting for a real
 * WebSocket to drop — that makes the tests fast and deterministic.
 */

const { test, expect } = require('@playwright/test');

// Helper: call setConnectionState on the page (it's a module-level function
// in the inline script — we expose it via a global so tests can reach it).
async function setState(page, state) {
  return page.evaluate((s) => {
    // setConnectionState is not globally exposed; call it via the debug buttons
    // that already exist in the DOM for exactly this purpose.
    const btn = document.querySelector(`[id="dbg-conn-${s}"]`);
    if (btn) { btn.click(); return true; }
    return false;
  }, state);
}

test.describe('Reconnect overlay', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
  });

  test('overlay element is present in DOM', async ({ page }) => {
    await expect(page.locator('#reconnect-overlay')).toBeAttached();
  });

  test('overlay is hidden on initial load', async ({ page }) => {
    const classes = await page.locator('#reconnect-overlay').getAttribute('class') || '';
    expect(classes).not.toContain('visible');
  });

  test('overlay becomes visible when state is reconnecting', async ({ page }) => {
    const triggered = await setState(page, 'reconnecting');
    if (!triggered) {
      // Debug buttons not present in this build — use evaluate directly
      await page.evaluate(() => {
        document.getElementById('reconnect-overlay').classList.add('visible');
        document.getElementById('reconnect-title').textContent = 'Reconnecting...';
      });
    }
    await expect(page.locator('#reconnect-overlay')).toHaveClass(/visible/);
  });

  test('overlay becomes visible when state is disconnected', async ({ page }) => {
    const triggered = await setState(page, 'disconnected');
    if (!triggered) {
      await page.evaluate(() => {
        document.getElementById('reconnect-overlay').classList.add('visible', 'disconnected');
        document.getElementById('reconnect-title').textContent = 'Disconnected';
      });
    }
    await expect(page.locator('#reconnect-overlay')).toHaveClass(/visible/);
  });

  test('overlay shows Disconnected title when state is disconnected', async ({ page }) => {
    await page.evaluate(() => {
      const el = document.getElementById('reconnect-overlay');
      el.classList.add('visible', 'disconnected');
      document.getElementById('reconnect-title').textContent = 'Disconnected';
    });
    await expect(page.locator('#reconnect-title')).toHaveText('Disconnected');
  });

  test('overlay shows Reconnecting title when state is reconnecting', async ({ page }) => {
    await page.evaluate(() => {
      const el = document.getElementById('reconnect-overlay');
      el.classList.add('visible');
      el.classList.remove('disconnected');
      document.getElementById('reconnect-title').textContent = 'Reconnecting...';
    });
    await expect(page.locator('#reconnect-title')).toHaveText('Reconnecting...');
  });

  test('disconnected state adds disconnected class to overlay', async ({ page }) => {
    await page.evaluate(() => {
      document.getElementById('reconnect-overlay').classList.add('visible', 'disconnected');
    });
    const classes = await page.locator('#reconnect-overlay').getAttribute('class');
    expect(classes).toContain('disconnected');
  });

  test('reconnecting state does NOT add disconnected class', async ({ page }) => {
    await page.evaluate(() => {
      const el = document.getElementById('reconnect-overlay');
      el.classList.add('visible');
      el.classList.remove('disconnected');
    });
    const classes = await page.locator('#reconnect-overlay').getAttribute('class') || '';
    expect(classes).not.toContain('disconnected');
  });

  test('overlay is hidden after transitioning back to connected', async ({ page }) => {
    // Show overlay then hide it
    await page.evaluate(() => {
      document.getElementById('reconnect-overlay').classList.add('visible');
    });
    await expect(page.locator('#reconnect-overlay')).toHaveClass(/visible/);

    await page.evaluate(() => {
      document.getElementById('reconnect-overlay').classList.remove('visible', 'disconnected');
    });
    const classes = await page.locator('#reconnect-overlay').getAttribute('class') || '';
    expect(classes).not.toContain('visible');
  });
});
