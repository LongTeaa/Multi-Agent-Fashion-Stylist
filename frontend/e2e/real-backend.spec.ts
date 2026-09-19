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
