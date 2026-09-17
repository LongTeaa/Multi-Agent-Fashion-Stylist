import { expect, test, type Page } from '@playwright/test';


async function expectBaselineAccessibility(page: Page): Promise<void> {
  const unnamedButtons = await page.locator('button').evaluateAll((buttons) =>
    buttons.filter((button) => {
      const text = button.textContent?.trim();
      return !text && !button.getAttribute('aria-label') && !button.getAttribute('title');
    }).length,
  );
  const missingImageAlt = await page.locator('img:not([alt])').count();
  const unlabeledInputs = await page.locator('input, textarea, select').evaluateAll((controls) =>
    controls.filter((control) => {
      const id = control.getAttribute('id');
      return !control.getAttribute('aria-label') && !(id && document.querySelector(`label[for="${id}"]`));
    }).length,
  );
  expect(unnamedButtons).toBe(0);
  expect(missingImageAlt).toBe(0);
  expect(unlabeledInputs).toBe(0);
}

for (const path of ['/', '/chat', '/wardrobe']) {
  test(`${path} remains usable at 375 px`, async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(path);
    await expect(page.locator('main')).toBeVisible();

    const dimensions = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    const overflowSources = await page.locator('body *').evaluateAll((elements) =>
      elements
        .filter((element) => element.getBoundingClientRect().right > document.documentElement.clientWidth + 1)
        .slice(0, 8)
        .map((element) => `${element.tagName.toLowerCase()}.${element.className}`),
    );
    expect(dimensions.scrollWidth, overflowSources.join('\n')).toBeLessThanOrEqual(dimensions.clientWidth + 1);
    await expectBaselineAccessibility(page);
  });
}
