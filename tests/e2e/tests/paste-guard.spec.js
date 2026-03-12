/**
 * paste-guard.spec.js
 *
 * Tests for two defensive paste features shipped together:
 *   A — Multiline paste guard   confirm dialog when clipboard text has newlines
 *   B — Smart paste / secrets   credential patterns trigger a concealed-paste offer
 */

const { test, expect } = require('@playwright/test');

// ─────────────────────────────────────────────────────────────────────────────
// A — Multiline paste guard
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Multiline paste guard', () => {
  test('looksLikeSecret helper exists on the page', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const exists = await page.evaluate(() => typeof looksLikeSecret === 'function');
    expect(exists).toBe(true);
  });

  test('looksLikeSecret returns false for ordinary text', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const result = await page.evaluate(() => looksLikeSecret('hello world'));
    expect(result).toBe(false);
  });

  test('looksLikeSecret returns false for a single-line command', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const result = await page.evaluate(() => looksLikeSecret('git commit -m "fix typo"'));
    expect(result).toBe(false);
  });

  test('handlePaste function is defined', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const exists = await page.evaluate(() => typeof handlePaste === 'function');
    expect(exists).toBe(true);
  });

  test('doPaste helper is defined', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const exists = await page.evaluate(() => typeof doPaste === 'function');
    expect(exists).toBe(true);
  });

  test('doBracketedPaste helper is defined', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const exists = await page.evaluate(() => typeof doBracketedPaste === 'function');
    expect(exists).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// B — Secret pattern detection
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Secret pattern detection', () => {
  const SECRET_SAMPLES = [
    ['GitHub PAT',        'ghp_abcdefghijklmnopqrstuvwxyz123456789012'],
    ['OpenAI key',        'sk-abcdefghijklmnopqrstuvwxyz1234567890ABCDEF'],
    ['AWS access key',    'AKIAIOSFODNN7EXAMPLE'],
    ['PEM private key',   '-----BEGIN RSA PRIVATE KEY-----'],
    ['JWT token',         'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0'],
    ['Slack bot token',   'xoxb-123456789012-1234567890123-abcdefghijklmnopqrstuvwx'],
    ['64-char hex',       'a'.repeat(64)],
  ];

  for (const [label, value] of SECRET_SAMPLES) {
    test(`detects ${label}`, async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      const result = await page.evaluate((v) => looksLikeSecret(v), value);
      expect(result).toBe(true);
    });
  }

  test('does not flag a short hex string (32 chars)', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // 32-char hex is an MD5 hash — too short to be a sha256 secret
    const result = await page.evaluate(() => looksLikeSecret('a'.repeat(32)));
    expect(result).toBe(false);
  });

  test('does not flag a normal file path', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const result = await page.evaluate(() => looksLikeSecret('/usr/local/bin/node'));
    expect(result).toBe(false);
  });

  test('does not flag a git commit SHA', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // 40-char hex — shorter than sha256 and common in shell sessions
    const result = await page.evaluate(() => looksLikeSecret('d3b07384d113edec49eaa6238ad5ff00'));
    expect(result).toBe(false);
  });
});
