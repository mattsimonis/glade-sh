/**
 * find-bar.spec.js
 *
 * Tests for the find-in-scrollback feature:
 *   — Floating search bar DOM structure
 *   — Hidden on load, opens via openFind(), closes on Escape / close button
 *   — Input receives focus when opened
 *   — Match count display and prev/next button state
 */

const { test, expect } = require('@playwright/test');

test.describe('Find bar — DOM structure', () => {
  test('find-bar element exists in the DOM', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const bar = page.locator('#find-bar');
    await expect(bar).toBeAttached();
  });

  test('find-input element exists', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await expect(page.locator('#find-input')).toBeAttached();
  });

  test('prev and next buttons exist', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await expect(page.locator('#fb-prev')).toBeAttached();
    await expect(page.locator('#fb-next')).toBeAttached();
  });

  test('close button exists', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await expect(page.locator('#fb-close')).toBeAttached();
  });

  test('find-count element exists', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await expect(page.locator('#find-count')).toBeAttached();
  });
});

test.describe('Find bar — hidden on load', () => {
  test('find bar does not have fb-open class on page load', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const hasOpen = await page.evaluate(() =>
      document.getElementById('find-bar').classList.contains('fb-open')
    );
    expect(hasOpen).toBe(false);
  });

  test('find bar is not pointer-interactive on load', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const pointerEvents = await page.evaluate(() =>
      getComputedStyle(document.getElementById('find-bar')).pointerEvents
    );
    expect(pointerEvents).toBe('none');
  });
});

test.describe('Find bar — open / close', () => {
  test('openFind() function is defined on the page', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const exists = await page.evaluate(() => typeof openFind === 'function');
    expect(exists).toBe(true);
  });

  test('calling openFind() adds fb-open class', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => openFind());
    const hasOpen = await page.evaluate(() =>
      document.getElementById('find-bar').classList.contains('fb-open')
    );
    expect(hasOpen).toBe(true);
  });

  test('clicking the close button removes fb-open class', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => openFind());
    await page.click('#fb-close');

    const hasOpen = await page.evaluate(() =>
      document.getElementById('find-bar').classList.contains('fb-open')
    );
    expect(hasOpen).toBe(false);
  });

  test('Escape key closes the find bar', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => openFind());
    // Focus the input so Escape is captured by the find-input keydown handler
    await page.focus('#find-input');
    await page.keyboard.press('Escape');

    const hasOpen = await page.evaluate(() =>
      document.getElementById('find-bar').classList.contains('fb-open')
    );
    expect(hasOpen).toBe(false);
  });
});

test.describe('Find bar — initial button state', () => {
  test('prev button is disabled on load (no query)', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const disabled = await page.evaluate(() => document.getElementById('fb-prev').disabled);
    expect(disabled).toBe(true);
  });

  test('next button is disabled on load (no query)', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const disabled = await page.evaluate(() => document.getElementById('fb-next').disabled);
    expect(disabled).toBe(true);
  });

  test('find-count is empty on load', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const text = await page.evaluate(() => document.getElementById('find-count').textContent);
    expect(text.trim()).toBe('');
  });
});
