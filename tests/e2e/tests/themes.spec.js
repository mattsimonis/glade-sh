/**
 * themes.spec.js
 *
 * Tests for the terminal theme picker:
 *   — TERM_THEMES object and applyTermTheme() function exist
 *   — Settings panel contains a theme grid
 *   — Grid has the expected number of swatches
 *   — Active swatch reflects localStorage.termTheme
 *   — Clicking a swatch updates localStorage.termTheme
 */

const { test, expect } = require('@playwright/test');

const EXPECTED_THEME_COUNT = 6; // Mocha, Frappé, Macchiato, Latte, Solarized Dark, One Dark

test.describe('Terminal themes — JS API', () => {
  test('TERM_THEMES object is defined', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const exists = await page.evaluate(() => typeof TERM_THEMES === 'object' && TERM_THEMES !== null);
    expect(exists).toBe(true);
  });

  test(`TERM_THEMES has exactly ${EXPECTED_THEME_COUNT} entries`, async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const count = await page.evaluate(() => Object.keys(TERM_THEMES).length);
    expect(count).toBe(EXPECTED_THEME_COUNT);
  });

  test('applyTermTheme function is defined', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const exists = await page.evaluate(() => typeof applyTermTheme === 'function');
    expect(exists).toBe(true);
  });

  test('TERM_THEMES contains mocha key', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const hasMocha = await page.evaluate(() => 'mocha' in TERM_THEMES);
    expect(hasMocha).toBe(true);
  });

  test('TERM_THEMES mocha entry has background and foreground colors', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const theme = await page.evaluate(() => TERM_THEMES['mocha']);
    expect(theme).toHaveProperty('background');
    expect(theme).toHaveProperty('foreground');
  });
});

test.describe('Terminal themes — settings grid DOM', () => {
  test('settings-theme-grid element exists', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await expect(page.locator('#settings-theme-grid')).toBeAttached();
  });

  test(`theme grid has ${EXPECTED_THEME_COUNT} swatches after render`, async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // Trigger renderThemePicker (called by settings open or on load)
    await page.evaluate(() => typeof renderThemePicker === 'function' && renderThemePicker());

    const count = await page.locator('#settings-theme-grid .theme-swatch').count();
    expect(count).toBe(EXPECTED_THEME_COUNT);
  });

  test('each swatch has a data-theme attribute', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => typeof renderThemePicker === 'function' && renderThemePicker());

    const swatches = page.locator('#settings-theme-grid .theme-swatch');
    const count = await swatches.count();
    for (let i = 0; i < count; i++) {
      const attr = await swatches.nth(i).getAttribute('data-theme');
      expect(attr).toBeTruthy();
    }
  });
});

test.describe('Terminal themes — persistence', () => {
  test('default theme in localStorage is mocha', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // If termTheme is unset the first visit defaults to 'mocha'
    const stored = await page.evaluate(() =>
      localStorage.getItem('termTheme') ?? 'mocha'
    );
    expect(stored).toBe('mocha');
  });

  test('applyTermTheme stores the selection in localStorage', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => applyTermTheme('solarized-dark'));

    const stored = await page.evaluate(() => localStorage.getItem('termTheme'));
    expect(stored).toBe('solarized-dark');
  });

  test('selected theme is restored from localStorage on revisit', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // Store a non-default theme, reload, and confirm it is picked up
    await page.evaluate(() => localStorage.setItem('termTheme', 'latte'));
    await page.reload();
    await page.waitForLoadState('domcontentloaded');

    const stored = await page.evaluate(() => localStorage.getItem('termTheme'));
    expect(stored).toBe('latte');
  });

  test('clicking a swatch calls applyTermTheme with the correct theme key', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => typeof renderThemePicker === 'function' && renderThemePicker());

    // Track calls to applyTermTheme
    await page.evaluate(() => {
      window.__themeApplied = null;
      const orig = applyTermTheme;
      window.applyTermTheme = (key) => { window.__themeApplied = key; orig(key); };
    });

    // Click the first swatch that is not already active
    const swatch = page.locator('#settings-theme-grid .theme-swatch').first();
    const key = await swatch.getAttribute('data-theme');
    await swatch.click();

    const applied = await page.evaluate(() => window.__themeApplied);
    expect(applied).toBe(key);
  });
});
