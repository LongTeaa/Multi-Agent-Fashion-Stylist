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

test('inventory separates item groups and searches Vietnamese aliases through the real API', async ({ page }) => {
  const userId = crypto.randomUUID();
  const headers = { 'X-User-Id': userId };
  const image = execFileSync('python', ['-c',
    'from PIL import Image; from io import BytesIO; import sys; b=BytesIO(); Image.new("RGB",(160,200),"grey").save(b,format="PNG"); sys.stdout.buffer.write(b.getvalue())'], { cwd: backendDir });
  const specs = [
    [{ category: 'footwear', sub_category: 'sneakers', primary_color: 'white' },
      { category: 'footwear', sub_category: 'derby', primary_color: 'black' }],
    [{ category: 'bottom', sub_category: 'jeans', primary_color: 'blue' },
      { category: 'bottom', sub_category: 'pleated_skirt', primary_color: 'black' }],
  ];
  for (const types of specs) {
    const upload = await page.request.post(`${apiBase}/api/v1/ingestions`, {
      headers, multipart: { 'images[]': { name: 'garment.png', mimeType: 'image/png', buffer: image } },
    });
    expect(upload.status()).toBe(202);
    const batch = (await upload.json()).data.batch_id;
    await expect.poll(async () => (await (await page.request.get(`${apiBase}/api/v1/ingestions/${batch}`, { headers })).json()).data.status).toBe('needs_review');
    const review = (await (await page.request.get(`${apiBase}/api/v1/ingestions/${batch}`, { headers })).json()).data;
    expect(review.detections).toHaveLength(2);
    const confirmed = await page.request.post(`${apiBase}/api/v1/ingestions/${batch}/confirm`, {
      headers, data: { confirmations: review.detections.map((d: { detection_id: string }, index: number) => ({
        detection_id: d.detection_id, accepted: true, custom_attributes: types[index],
      })) },
    });
    expect(confirmed.status()).toBe(200);
  }
  await page.addInitScript((id) => localStorage.setItem('fashion_stylist_user_id', id), userId);
  await page.goto('/wardrobe');
  const cards = page.locator('[data-testid^="wardrobe-item-card-"]');
  await expect(cards).toHaveCount(4);
  await page.getByTestId('category-filter-pants').click();
  await expect(cards).toHaveCount(1);
  await expect(cards.first()).toContainText('Quần jeans');
  await page.getByTestId('category-filter-skirt').click();
  await expect(cards).toHaveCount(1);
  await expect(cards.first()).toContainText('Chân váy xếp ly');
  await page.getByTestId('category-filter-all').click();
  const search = page.getByTestId('wardrobe-search-input');
  await search.fill('giay');
  await expect(cards).toHaveCount(4);
  await page.getByRole('button', { name: 'Tìm', exact: true }).click();
  await expect(cards).toHaveCount(2);
  await page.screenshot({ path: 'test-results/taxonomy-search-desktop.png', fullPage: true });
  await search.fill('giày đen');
  await search.press('Enter');
  await expect(cards).toHaveCount(1);
  await expect(cards.first()).toContainText('Giày Derby');
  await page.setViewportSize({ width: 375, height: 812 });
  await page.screenshot({ path: 'test-results/taxonomy-search-mobile.png', fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

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
  await expect(page.getByText('Ngữ Cảnh Được AI Nhận Diện', { exact: false })).toHaveCount(0);
  expect(new Set(chat.recommendations.map((r: { explanation_vi: string }) => r.explanation_vi)).size).toBe(chat.recommendations.length);
  await page.screenshot({ path: 'test-results/recommendations-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.screenshot({ path: 'test-results/recommendations-mobile.png', fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });

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
  await expect(photos.nth(1)).toHaveAttribute('aria-pressed', 'true');
  await details.locator('summary').click();
  const material = details.locator('select').filter({ has: page.locator('option[value="linen"]') });
  await material.selectOption('linen');
  await details.locator('summary').click();
  await expect(details).toHaveJSProperty('open', false);

  await page.getByRole('button', { name: 'Chỉnh vùng cắt', exact: true }).click();
  await page.getByRole('button', { name: 'Khung AI gốc', exact: true }).click();
  const restore = page.waitForResponse(r => r.request().method() === 'PATCH' && r.url().endsWith('/crop'));
  await page.getByRole('button', { name: 'Lưu vùng cắt', exact: true }).click();
  const restored = (await (await restore).json()).data;
  expect(restored.detections.some((d: { bounding_box: number[]; raw_bounding_box: number[] | null }) =>
    d.raw_bounding_box && JSON.stringify(d.bounding_box) === JSON.stringify(d.raw_bounding_box))).toBe(true);
  await page.getByRole('button', { name: 'Chỉnh vùng cắt', exact: true }).click();
  await page.getByRole('button', { name: 'Lưu vùng cắt', exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'test-results/review-closure-desktop.png', fullPage: false });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.getByRole('button', { name: 'Lưu vùng cắt', exact: true }).scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await page.screenshot({ path: 'test-results/review-closure-mobile.png', fullPage: false });
  await page.getByRole('button', { name: 'Chỉnh vùng cắt', exact: true }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/confirmation-review-mobile.png', fullPage: true });
  const review = await page.request.get(`${apiBase}/api/v1/ingestions/${batch}`, { headers: { 'X-User-Id': userId } });
  expect((await review.json()).data.detections.some((d: { raw_bounding_box: number[] | null }) => d.raw_bounding_box !== null)).toBe(true);
  const confirmation = page.waitForResponse(r => r.url().endsWith('/confirm') && r.request().method() === 'POST');
  await page.getByRole('button', { name: /Lưu vào tủ đồ/ }).click();
  expect((await confirmation).status()).toBe(200);
  const wardrobe = await page.request.get(`${apiBase}/api/v1/wardrobe/items`, { headers: { 'X-User-Id': userId } });
  expect((await wardrobe.json()).data.items.some((item: { material: string }) => item.material === 'linen')).toBe(true);
});

for (const count of [1, 10]) {
  test(`upload ${count} distinct photos retains every source after reload`, async ({ page }) => {
    test.setTimeout(60_000);
    const userId = crypto.randomUUID();
    await page.addInitScript((id) => localStorage.setItem('fashion_stylist_user_id', id), userId);
    const encoded = JSON.parse(execFileSync('python', ['-c',
      'from PIL import Image; from io import BytesIO; import base64,json,sys; output=[]\nfor i in range(int(sys.argv[1])):\n b=BytesIO(); Image.new("RGB",(160,200),(20+i*17,60,120)).save(b,format="PNG"); output.append(base64.b64encode(b.getvalue()).decode())\nprint(json.dumps(output))', String(count)],
      { cwd: backendDir, encoding: 'utf8' })) as string[];
    await page.goto('/wardrobe');
    await page.getByTestId('btn-add-garment').click();
    await page.getByLabel('Chọn ảnh trang phục để tải lên').setInputFiles(encoded.map((value, i) => ({
      name: `photo-${i}.png`, mimeType: 'image/png', buffer: Buffer.from(value, 'base64'),
    })));
    await page.getByRole('button', { name: /Tiến hành phân tích/i }).click();
    const photos = page.getByRole('button').filter({ has: page.locator('img') });
    await expect(photos).toHaveCount(count, { timeout: 30_000 });
    await photos.nth(count - 1).click();
    await expect(photos.nth(count - 1)).toHaveAttribute('aria-pressed', 'true');
    await page.reload();
    await page.getByTestId('btn-add-garment').click();
    await expect(photos).toHaveCount(count);
    await expect(photos.nth(count - 1)).toHaveAttribute('aria-pressed', 'true');
    const batch = await page.evaluate(() => sessionStorage.getItem('active_ingestion_batch_id'));
    const review = (await (await page.request.get(`${apiBase}/api/v1/ingestions/${batch}`,
      { headers: { 'X-User-Id': userId } })).json()).data;
    expect(new Set(review.source_images.map((source: { media_asset_id: string }) => source.media_asset_id)).size).toBe(count);
    expect(new Set(review.detections.map((d: { source_media_asset_id: string }) => d.source_media_asset_id)).size).toBe(count);
  });
}
