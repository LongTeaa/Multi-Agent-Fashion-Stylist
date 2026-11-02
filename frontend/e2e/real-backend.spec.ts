import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { expect, test } from '@playwright/test';

const apiBase = 'http://127.0.0.1:8011';
const backendDir = path.resolve(process.cwd(), '../backend');
const fixtureUserId = execFileSync(
  'python',
  ['-c', 'from app.core.seed import GOLDEN_USER_ID; print(GOLDEN_USER_ID)'],
  { cwd: backendDir, encoding: 'utf8' }
).trim();

test('browser uses real API, persisted outfits, private media, actions, and try-on fallback', async ({ page }) => {
  await page.addInitScript((userId) => {
    localStorage.setItem('fashion_stylist_user_id', userId);
  }, fixtureUserId);
  await page.goto('/chat');

  const chatResponsePromise = page.waitForResponse((response) =>
    response.url() === `${apiBase}/api/v1/stylist/chat`
  );
  await page.getByLabel('Nhu cầu phối đồ của bạn').fill(
    'Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?'
  );
  await page.getByRole('button', { name: /Phối Đồ/i }).click();
  const chatResponse = await chatResponsePromise;
  expect(chatResponse.status()).toBe(200);
  expect(chatResponse.request().headers()['x-user-id']).toBe(fixtureUserId);
  const chat = (await chatResponse.json()).data;
  expect(chat.recommendations.length).toBeGreaterThan(0);

  const outfit = chat.recommendations[0];
  const card = page.getByTestId('outfit-recommendation-card').first();
  await expect(card).toHaveAttribute('data-outfit-id', outfit.outfit_id);
  await expect.poll(() => card.locator('img').first().evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);

  const headers = { 'X-User-Id': fixtureUserId };
  const detail = await page.request.get(`${apiBase}/api/v1/outfits/${outfit.outfit_id}`, { headers });
  expect(detail.status()).toBe(200);
  expect((await detail.json()).data.id).toBe(outfit.outfit_id);
  const mediaUrl = outfit.items[0].image_url;
  expect((await page.request.get(`${apiBase}${mediaUrl}`)).status()).toBe(422);
  expect((await page.request.get(`${apiBase}${mediaUrl}`, { headers })).status()).toBe(200);

  await card.getByRole('button', { name: 'Lưu bộ đồ này' }).click();
  await expect(card.getByRole('button', { name: 'Bỏ lưu bộ đồ này' })).toBeVisible();
  await card.getByRole('button', { name: 'Xác nhận đã mặc bộ trang phục này hôm nay' }).click();
  await expect(card).toContainText(/Đã mặc hôm nay/i);
  await card.getByRole('button', { name: 'Đánh giá 5 sao' }).click();

  const updated = await page.request.get(`${apiBase}/api/v1/outfits/${outfit.outfit_id}`, { headers });
  expect(updated.status()).toBe(200);
  const updatedOutfit = (await updated.json()).data;
  expect(updatedOutfit.is_bookmarked).toBe(true);
  expect(updatedOutfit.times_worn).toBe(1);
  expect(updatedOutfit.user_rating).toBe(5);

  await card.getByRole('button', { name: 'Xem ảnh minh họa bộ trang phục' }).click();
  const dialog = page.getByRole('dialog', { name: 'Xem trước bộ trang phục' });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('Moodboard dự phòng');
  await expect.poll(() => dialog.locator('img').first().evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
});


test('multi-photo review switches sources and persists a corrected crop', async ({ page }) => {
  const userId = crypto.randomUUID();
  await page.addInitScript((id) => localStorage.setItem('fashion_stylist_user_id', id), userId);
  await page.goto('/wardrobe');
  await page.getByTestId('btn-add-garment').click();
  const image = execFileSync('python', ['-c',
    'from PIL import Image; from io import BytesIO; import sys; b=BytesIO(); Image.new("RGB",(160,200),"red").save(b,format="PNG"); sys.stdout.buffer.write(b.getvalue())'], { cwd: backendDir });
  const second = execFileSync('python', ['-c',
    'from PIL import Image; from io import BytesIO; import sys; b=BytesIO(); Image.new("RGB",(160,200),"blue").save(b,format="PNG"); sys.stdout.buffer.write(b.getvalue())'], { cwd: backendDir });
  await page.getByLabel('Chọn ảnh trang phục để tải lên').setInputFiles([
    { name: 'red.png', mimeType: 'image/png', buffer: image },
    { name: 'blue.png', mimeType: 'image/png', buffer: second },
  ]);
  const upload = page.waitForResponse(r => r.url() === `${apiBase}/api/v1/ingestions` && r.request().method() === 'POST');
  await page.getByRole('button', { name: /Tiến hành phân tích/i }).click();
  const batch = (await (await upload).json()).data.batch_id;
  const photos = page.getByRole('button').filter({ has: page.locator('img') });
  await expect(photos).toHaveCount(2);
  await photos.nth(1).click();
  await expect(photos.nth(1)).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('note')).toContainText('Chọn những món muốn giữ');
  const details = page.locator('details').first();
  await expect(details).toHaveJSProperty('open', false);
  await page.screenshot({ path: 'test-results/confirmation-review-desktop.png', fullPage: true });
  await page.getByRole('button', { name: 'Chỉnh vùng cắt', exact: true }).click();
  await page.getByRole('button', { name: 'Lấy toàn ảnh', exact: true }).click();
  const patch = page.waitForResponse(r => r.request().method() === 'PATCH' && r.url().endsWith('/crop'));
  await page.getByRole('button', { name: 'Lưu vùng cắt', exact: true }).click();
  expect((await patch).status()).toBe(200);
  await page.reload();
  await page.getByTestId('btn-add-garment').click();
  await expect(photos).toHaveCount(2);
  await details.locator('summary').click();
  const material = details.locator('select').filter({ has: page.locator('option[value="linen"]') });
  await material.selectOption('linen');
  await details.locator('summary').click();
  await expect(details).toHaveJSProperty('open', false);

  await page.getByRole('button', { name: 'Chỉnh vùng cắt', exact: true }).click();
  await page.getByRole('button', { name: 'Lưu vùng cắt', exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'test-results/multi-photo-review.png', fullPage: false });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.getByRole('button', { name: 'Lưu vùng cắt', exact: true }).scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await page.screenshot({ path: 'test-results/multi-photo-review-mobile.png', fullPage: false });
  await page.getByRole('button', { name: 'Chỉnh vùng cắt', exact: true }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/confirmation-review-mobile.png', fullPage: true });
  const review = await page.request.get(`${apiBase}/api/v1/ingestions/${batch}`, { headers: { 'X-User-Id': userId } });
  expect((await review.json()).data.detections.some((d: { bounding_box: number[] }) => JSON.stringify(d.bounding_box) === '[0,0,1,1]')).toBe(true);
  const confirmation = page.waitForResponse(r => r.url().endsWith('/confirm') && r.request().method() === 'POST');
  await page.getByRole('button', { name: /Lưu vào tủ đồ/ }).click();
  expect((await confirmation).status()).toBe(200);
  const wardrobe = await page.request.get(`${apiBase}/api/v1/wardrobe/items`, { headers: { 'X-User-Id': userId } });
  expect((await wardrobe.json()).data.items.some((item: { material: string }) => item.material === 'linen')).toBe(true);
});
