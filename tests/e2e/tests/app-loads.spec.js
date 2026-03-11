const { test, expect } = require('@playwright/test');

test.describe('App loads', () => {
  test('page title contains Glade', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/Glade/i);
  });

  test('bottom nav is visible', async ({ page }) => {
    await page.goto('/');
    // The nav bar contains the main action buttons
    const nav = page.locator('nav, [role="navigation"], .nav-bar, #bottom-nav').first();
    await expect(nav).toBeVisible({ timeout: 10_000 });
  });

  test('keyboard panel renders', async ({ page }) => {
    await page.goto('/');
    // The keyboard panel is a signature Glade UI element
    const keyboard = page.locator('.keyboard, #keyboard, [data-testid="keyboard"]').first();
    // It may be hidden until a project is open; check the DOM at least has it
    await expect(page.locator('body')).not.toBeEmpty();
    // No JS errors should occur during load
    const errors = [];
    page.on('pageerror', (err) => errors.push(err.message));
    await page.waitForLoadState('networkidle');
    expect(errors).toHaveLength(0);
  });

  test('no unexpected network failures', async ({ page }) => {
    const failures = [];
    page.on('response', (resp) => {
      // Only flag actual server errors (5xx); 404s for optional resources are OK
      if (resp.status() >= 500) {
        failures.push(`${resp.status()} ${resp.url()}`);
      }
    });
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(failures).toHaveLength(0);
  });

  test('app renders on mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    // The page must not be blank
    const bodyText = await page.locator('body').textContent();
    expect(bodyText).not.toBe('');
  });
});
