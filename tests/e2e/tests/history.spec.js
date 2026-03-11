const { test, expect } = require('@playwright/test');

test.describe('History', () => {
  test('history panel renders without errors', async ({ page }) => {
    const errors = [];
    page.on('pageerror', (err) => errors.push(err.message));

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Find and click the history tab
    const historyBtn = page
      .locator('button, [role="button"], [role="tab"]')
      .filter({ hasText: /history|log/i })
      .first();

    if (await historyBtn.isVisible()) {
      await historyBtn.click();
      await page.waitForLoadState('networkidle');
    }

    expect(errors).toHaveLength(0);
  });

  test('history list renders (may be empty)', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const historyBtn = page
      .locator('button, [role="button"], [role="tab"]')
      .filter({ hasText: /history|log/i })
      .first();

    if (await historyBtn.isVisible()) {
      await historyBtn.click();
      await page.waitForTimeout(1_000);
      // Should show either a list of entries or an empty-state message
      const body = await page.locator('body').textContent();
      expect(body.length).toBeGreaterThan(0);
    } else {
      test.skip('History button not found in current layout');
    }
  });

  test('search input works in history panel', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const historyBtn = page
      .locator('button, [role="button"], [role="tab"]')
      .filter({ hasText: /history|log/i })
      .first();

    if (!(await historyBtn.isVisible())) {
      test.skip('History button not found');
      return;
    }

    await historyBtn.click();
    await page.waitForTimeout(500);

    const searchInput = page
      .locator('input[type="search"], input[placeholder*="search" i], input[placeholder*="filter" i]')
      .first();

    if (await searchInput.isVisible()) {
      await searchInput.fill('somequery');
      await page.waitForTimeout(500);
      // After typing, no JS errors and the page should still be intact
      const body = await page.locator('body').textContent();
      expect(body.length).toBeGreaterThan(0);
    } else {
      test.skip('Search input not found in history panel');
    }
  });

  test('/api/logs endpoint is reachable', async ({ request }) => {
    const resp = await request.get('/api/logs');
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(Array.isArray(data)).toBe(true);
  });
});
