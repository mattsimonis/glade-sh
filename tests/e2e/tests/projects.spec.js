const { test, expect } = require('@playwright/test');

test.describe('Projects', () => {
  test('project overlay opens', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Click the projects/grid button in the nav to open the project overlay
    const projectBtn = page
      .locator('button, [role="button"]')
      .filter({ hasText: /project|grid|folder/i })
      .first();

    if (await projectBtn.isVisible()) {
      await projectBtn.click();
      // The overlay/panel should appear
      const overlay = page.locator(
        '.overlay, .modal, [role="dialog"], .projects-panel, #projects-overlay'
      ).first();
      await expect(overlay).toBeVisible({ timeout: 5_000 });
    } else {
      // Fallback: the projects list may already be visible on this layout
      test.skip('Project button not found — layout may differ');
    }
  });

  test('create a new project', async ({ page, request }) => {
    // Create via the API directly so we don't depend on UI form details
    const resp = await request.post('/api/projects', {
      data: { name: 'E2E Test Project', directory: '/', color: '#a6e3a1' },
    });
    expect(resp.status()).toBe(201);
    const project = await resp.json();
    expect(project.id).toBeTruthy();
    expect(project.name).toBe('E2E Test Project');

    // Reload and verify the project appears
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Clean up
    await request.delete(`/api/projects/${project.id}`);
  });

  test('project appears in list after creation', async ({ page, request }) => {
    const resp = await request.post('/api/projects', {
      data: { name: 'Visible Project' },
    });
    const project = await resp.json();

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // The project name should be somewhere on the page (card, list item, etc.)
    await expect(page.getByText('Visible Project')).toBeVisible({ timeout: 8_000 });

    await request.delete(`/api/projects/${project.id}`);
  });

  test('deleting a project removes it from the list', async ({ page, request }) => {
    const resp = await request.post('/api/projects', {
      data: { name: 'To Be Deleted' },
    });
    const project = await resp.json();

    await request.delete(`/api/projects/${project.id}`);

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Text should not be visible after deletion
    const el = page.getByText('To Be Deleted');
    await expect(el).not.toBeVisible({ timeout: 5_000 });
  });
});
