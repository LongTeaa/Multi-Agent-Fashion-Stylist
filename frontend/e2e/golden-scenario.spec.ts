import { expect, test, type Page, type Route } from '@playwright/test';


const apiSuccess = (data: unknown) => ({ success: true, data });

async function json(route: Route, data: unknown): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(apiSuccess(data)),
  });
}

async function installApiMocks(page: Page): Promise<void> {
  await page.route('http://localhost:8000/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const headers = request.headers();

    // Verify identity boundary: X-User-Id must always be provided as a valid UUID
    const userId = headers['x-user-id'];
    expect(userId).toBeTruthy();
    expect(userId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);

    if (url.pathname === '/api/v1/stylist/chat') {
      await json(route, {
        request_id: 'request-golden-e2e',
        needs_clarification: false,
        clarification_question: null,
        context: {
          occasion: 'cafe',
          time_of_day: 'evening',
          event_date: '2026-09-17',
          location_text: null,
          environment: null,
          weather_condition: 'cool',
          temperature_celsius: null,
          target_formality_range: [2, 3],
          style_hints: ['smart_casual'],
          vibe_keywords: [],
          must_have: [],
          must_avoid: [],
          weather_source: 'user',
        },
        recommendations: [
          {
            outfit_id: 'outfit-golden-e2e',
            rank: 1,
            composite_score: 0.96,
            items: [
              { slot: 'top', item_id: 'white-polo', name: 'White Polo', image_url: null },
              { slot: 'bottom', item_id: 'navy-chinos', name: 'Navy Chinos', image_url: null },
              { slot: 'footwear', item_id: 'white-sneakers', name: 'White Sneakers', image_url: null },
            ],
            explanation_vi: 'Áo polo trắng, chinos navy và sneakers trắng cân bằng sự gọn gàng với cảm giác thoải mái cho buổi cafe trời mát.',
            applied_preferences: ['smart_casual'],
          },
        ],
        feedback_prompt_eligible: true,
        feedback_target_outfit_id: 'outfit-golden-e2e',
        warnings: [],
      });
      return;
    }

    if (url.pathname.endsWith('/bookmark')) {
      const body = request.postDataJSON() as { is_bookmarked: boolean };
      await json(route, {
        outfit_id: 'outfit-golden-e2e',
        is_bookmarked: body.is_bookmarked,
        updated_at: '2026-09-17T08:00:00Z',
      });
      return;
    }

    if (url.pathname.endsWith('/worn')) {
      await json(route, {
        outfit_id: 'outfit-golden-e2e',
        wear_log_id: 'wear-log-golden-e2e',
        worn_at: '2026-09-17T08:00:00Z',
        times_worn: 1,
        already_processed: false,
      });
      return;
    }

    if (url.pathname.endsWith('/rating')) {
      const body = request.postDataJSON() as { stars: number; source: string };
      await json(route, {
        rating_id: 'rating-golden-e2e',
        outfit_id: 'outfit-golden-e2e',
        stars: body.stars,
        source: body.source,
        ratings_count: 1,
        created_at: '2026-09-17T08:00:00Z',
        updated_at: '2026-09-17T08:00:00Z',
      });
      return;
    }

    if (url.pathname === '/api/v1/tryons') {
      await json(route, {
        tryon_id: 'tryon-golden-e2e',
        outfit_id: 'outfit-golden-e2e',
        image_url: '/api/v1/media/moodboard-e2e',
        render_kind: 'moodboard',
        fallback_used: true,
        duration_ms: 42,
        status: 'ready',
      });
      return;
    }

    if (url.pathname.startsWith('/api/v1/media/')) {
      await route.fulfill({ status: 204 });
      return;
    }

    await route.abort('failed');
  });
}

test('golden journey reaches persisted actions, cadence rating, and try-on fallback', async ({ page }) => {
  await installApiMocks(page);
  await page.goto('/chat');

  await page.getByLabel('Nhu cầu phối đồ của bạn').fill(
    'Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?',
  );
  await page.getByRole('button', { name: /Phối Đồ/i }).click();

  const card = page.getByTestId('outfit-recommendation-card');
  await expect(card).toHaveAttribute('data-outfit-id', 'outfit-golden-e2e');
  await expect(card).toContainText('White Polo');
  await expect(card).toContainText('Navy Chinos');
  await expect(card).toContainText('White Sneakers');

  await card.getByRole('button', { name: 'Lưu bộ đồ này' }).click();
  await expect(card.getByRole('button', { name: 'Bỏ lưu bộ đồ này' })).toBeVisible();

  await card.getByRole('button', { name: 'Xác nhận đã mặc bộ trang phục này hôm nay' }).click();
  await expect(card).toContainText(/Đã mặc hôm nay/i);

  const prompt = page.getByRole('region', { name: 'Khảo sát đánh giá gợi ý phối đồ' });
  await expect(prompt).toBeVisible();
  await prompt.getByRole('button', { name: 'Đánh giá 5 sao' }).click();
  await expect(prompt).toContainText('Cảm ơn bạn đã phản hồi!');

  await card.getByRole('button', { name: 'Xem ảnh minh họa bộ trang phục' }).click();
  const dialog = page.getByRole('dialog', { name: 'Xem trước bộ trang phục' });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('Moodboard dự phòng');
  await expect(dialog).toContainText('không mô phỏng chính xác kích thước hoặc độ vừa vặn');
});
