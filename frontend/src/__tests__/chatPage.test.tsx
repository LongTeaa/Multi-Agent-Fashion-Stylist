import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import ChatPage from '@/app/chat/page';
import * as apiModule from '@/lib/api';
import { ApiError } from '@/lib/api';
import type { StylistChatResponseData } from '@/types/chat';

describe('Chat Page & Components Integration', () => {
  const mockSuccessData: StylistChatResponseData = {
    request_id: 'req-page-123',
    needs_clarification: false,
    clarification_question: null,
    context: {
      occasion: 'cafe',
      time_of_day: 'morning',
      event_date: null,
      location_text: 'Hà Nội',
      environment: 'indoor',
      weather_condition: 'nắng nhẹ',
      temperature_celsius: 25,
      target_formality_range: [2, 3],
      style_hints: ['casual', 'minimalist'],
      vibe_keywords: ['thoải mái'],
      must_have: [],
      must_avoid: [],
      weather_source: 'user',
    },
    recommendations: [
      {
        outfit_id: 'outfit-persisted-1',
        rank: 1,
        composite_score: 0.95,
        items: [
          {
            slot: 'top',
            item_id: 'top-item-1',
            name: 'Áo sơ mi linen trắng',
            image_url: '/api/v1/media/linen-top',
          },
          {
            slot: 'bottom',
            item_id: 'bottom-item-1',
            name: 'Quần chinos be',
            image_url: null,
          },
          {
            slot: 'shoes',
            item_id: 'shoes-item-1',
            name: 'Giày loafer nâu',
            image_url: '/api/v1/media/loafer',
          },
        ],
        explanation_vi: 'Set đồ thoáng mát và thanh lịch cho buổi cafe sáng.',
        applied_preferences: ['Tối giản', 'Gam màu trung tính'],
      },
    ],
    feedback_prompt_eligible: false,
    feedback_target_outfit_id: null,
    warnings: [],
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it('renders chat page header, title, and initial composer', () => {
    render(<ChatPage />);

    expect(screen.getByText('Trợ Lý Phối Đồ Stylist AI')).toBeDefined();
    expect(screen.getByRole('form', { name: /Khung gửi câu hỏi tư vấn phối đồ/i })).toBeDefined();

    const submitBtn = screen.getByRole('button', { name: /Phối Đồ/i });
    expect(submitBtn).toBeDefined();
    expect(submitBtn.hasAttribute('disabled')).toBe(true);

    expect(screen.getByText(/Gợi ý bối cảnh thường gặp:/i)).toBeDefined();
  });

  it('fills composer with suggested prompt when pill is clicked', () => {
    render(<ChatPage />);

    const pill = screen.getByText(/Đi cafe ngoài trời ở Đà Lạt/i);
    fireEvent.click(pill);

    const textarea = screen.getByLabelText(/Nhu cầu phối đồ của bạn/i) as HTMLTextAreaElement;
    expect(textarea.value).toContain('Đi cafe ngoài trời ở Đà Lạt');

    const submitBtn = screen.getByRole('button', { name: /Phối Đồ/i });
    expect(submitBtn.hasAttribute('disabled')).toBe(false);
  });

  it('submits query and renders successful recommendations', async () => {
    vi.spyOn(apiModule, 'sendStylistChat').mockResolvedValueOnce(mockSuccessData);

    render(<ChatPage />);

    const textarea = screen.getByLabelText(/Nhu cầu phối đồ của bạn/i);
    fireEvent.change(textarea, { target: { value: 'Đi cafe sáng cuối tuần' } });

    const submitBtn = screen.getByRole('button', { name: /Phối Đồ/i });
    fireEvent.click(submitBtn);

    // Wait for recommendation card to appear
    await waitFor(() => {
      expect(screen.getByText(/Gợi Ý Phối Đồ Số 1/i)).toBeDefined();
    });

    expect(screen.getByText('Áo sơ mi linen trắng')).toBeDefined();
    expect(screen.getByText('Quần chinos be')).toBeDefined();
    expect(screen.getByText('Giày loafer nâu')).toBeDefined();
    expect(screen.getByText(/Set đồ thoáng mát và thanh lịch/i)).toBeDefined();
    expect(screen.getByText('95%')).toBeDefined();

    // Verify persisted outfit ID is attached to card
    const card = screen.getByTestId('outfit-recommendation-card');
    expect(card.getAttribute('data-outfit-id')).toBe('outfit-persisted-1');
  });

  it('renders clarification banner when needs_clarification is true and focuses composer on click', async () => {
    vi.spyOn(apiModule, 'sendStylistChat').mockResolvedValueOnce({
      request_id: 'req-clarify',
      needs_clarification: true,
      clarification_question: 'Bạn muốn dự tiệc ngoài trời hay trong nhà?',
      context: {
        target_formality_range: [],
        style_hints: [],
        vibe_keywords: [],
        must_have: [],
        must_avoid: [],
        weather_source: 'default',
      },
      recommendations: [],
      feedback_prompt_eligible: false,
      feedback_target_outfit_id: null,
      warnings: [],
    });

    render(<ChatPage />);

    const textarea = screen.getByLabelText(/Nhu cầu phối đồ của bạn/i);
    fireEvent.change(textarea, { target: { value: 'Đi tiệc' } });

    const submitBtn = screen.getByRole('button', { name: /Phối Đồ/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByRole('region', { name: /Yêu cầu làm rõ từ Stylist AI/i })).toBeDefined();
    });

    expect(screen.getByText('Bạn muốn dự tiệc ngoài trời hay trong nhà?')).toBeDefined();

    // Click "Trả lời câu hỏi" button
    const answerBtn = screen.getByRole('button', { name: /Trả lời câu hỏi/i });
    fireEvent.click(answerBtn);

    // Verify textarea has focus
    expect(document.activeElement).toBe(textarea);
  });

  it('renders domain error WARDROBE_EMPTY with direct link to wardrobe page', async () => {
    vi.spyOn(apiModule, 'sendStylistChat').mockRejectedValueOnce(
      new ApiError('Tủ đồ chưa có trang phục.', 'WARDROBE_EMPTY', 422)
    );

    render(<ChatPage />);

    const textarea = screen.getByLabelText(/Nhu cầu phối đồ của bạn/i);
    fireEvent.change(textarea, { target: { value: 'Đi dạo phố' } });

    fireEvent.click(screen.getByRole('button', { name: /Phối Đồ/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined();
    });

    expect(screen.getByText('Tủ Đồ Chưa Có Trang Phục')).toBeDefined();
    expect(screen.getByRole('link', { name: /Số Hóa Tủ Đồ Ngay/i })).toBeDefined();
  });

  it('renders domain error NO_COMPLETE_OUTFIT with contextual guidance', async () => {
    vi.spyOn(apiModule, 'sendStylistChat').mockRejectedValueOnce(
      new ApiError('Không thể tạo bộ phối hoàn chỉnh.', 'NO_COMPLETE_OUTFIT', 422)
    );

    render(<ChatPage />);

    const textarea = screen.getByLabelText(/Nhu cầu phối đồ của bạn/i);
    fireEvent.change(textarea, { target: { value: 'Đi dạ hội sang trọng' } });

    fireEvent.click(screen.getByRole('button', { name: /Phối Đồ/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined();
    });

    expect(screen.getByText('Không Thể Tạo Bộ Phối Hoàn Chỉnh')).toBeDefined();
  });

  it('strictly enforces maxLength constraints on query (1000) and location (200) inputs', () => {
    const sendSpy = vi.spyOn(apiModule, 'sendStylistChat');

    render(<ChatPage />);

    const textarea = screen.getByLabelText(/Nhu cầu phối đồ của bạn/i) as HTMLTextAreaElement;
    expect(textarea.getAttribute('maxlength')).toBe('1000');

    // Click "+ Thêm địa điểm"
    const addLocationBtn = screen.getByRole('button', { name: /\+ Thêm địa điểm/i });
    fireEvent.click(addLocationBtn);

    const locationInput = screen.getByPlaceholderText(/Ví dụ: Hà Nội, Đà Lạt/i) as HTMLInputElement;
    expect(locationInput.getAttribute('maxlength')).toBe('200');

    // Attempting to submit via Enter when text is somehow over limit
    const longQuery = 'A'.repeat(1005);
    fireEvent.change(textarea, { target: { value: longQuery } });
    fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter' });

    expect(sendSpy).not.toHaveBeenCalled();
  });

  it('renders RatingPrompt when feedback_prompt_eligible is true and target outfit exists', async () => {
    vi.spyOn(apiModule, 'sendStylistChat').mockResolvedValueOnce({
      ...mockSuccessData,
      feedback_prompt_eligible: true,
      feedback_target_outfit_id: 'outfit-persisted-1',
    });

    render(<ChatPage />);

    const textarea = screen.getByLabelText(/Nhu cầu phối đồ của bạn/i);
    fireEvent.change(textarea, { target: { value: 'Đi cafe sáng cuối tuần' } });

    const submitBtn = screen.getByRole('button', { name: /Phối Đồ/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByRole('region', { name: /Khảo sát đánh giá gợi ý phối đồ/i })).toBeDefined();
    });

    expect(screen.getByText('Bạn chấm gợi ý vừa rồi mấy sao?')).toBeDefined();
    expect(screen.getByText('Set #1')).toBeDefined();
  });

  it('dismisses RatingPrompt and calls dismissFeedbackPrompt when "Để sau" is clicked', async () => {
    vi.spyOn(apiModule, 'sendStylistChat').mockResolvedValueOnce({
      ...mockSuccessData,
      feedback_prompt_eligible: true,
      feedback_target_outfit_id: 'outfit-persisted-1',
    });
    const dismissSpy = vi.spyOn(apiModule, 'dismissFeedbackPrompt').mockResolvedValueOnce({
      cooldown_remaining: 3,
      dismissed: true,
    });

    render(<ChatPage />);

    const textarea = screen.getByLabelText(/Nhu cầu phối đồ của bạn/i);
    fireEvent.change(textarea, { target: { value: 'Đi cafe sáng' } });
    fireEvent.click(screen.getByRole('button', { name: /Phối Đồ/i }));

    await waitFor(() => {
      expect(screen.getByRole('region', { name: /Khảo sát đánh giá gợi ý phối đồ/i })).toBeDefined();
    });

    const dismissBtn = screen.getByRole('button', { name: /Để sau/i });
    fireEvent.click(dismissBtn);

    await waitFor(() => {
      expect(dismissSpy).toHaveBeenCalled();
      expect(screen.queryByRole('region', { name: /Khảo sát đánh giá gợi ý phối đồ/i })).toBeNull();
    });
  });

  it('submits rating via RatingPrompt, updates OutfitCard stars, and hides prompt', async () => {
    vi.spyOn(apiModule, 'sendStylistChat').mockResolvedValueOnce({
      ...mockSuccessData,
      feedback_prompt_eligible: true,
      feedback_target_outfit_id: 'outfit-persisted-1',
    });
    const rateSpy = vi.spyOn(apiModule, 'rateOutfit').mockResolvedValueOnce({
      rating_id: 'rating-prompted-1',
      outfit_id: 'outfit-persisted-1',
      stars: 5,
      source: 'prompted',
      ratings_count: 1,
      created_at: '2026-09-15T08:00:00Z',
      updated_at: '2026-09-15T08:00:00Z',
    });

    render(<ChatPage />);

    const textarea = screen.getByLabelText(/Nhu cầu phối đồ của bạn/i);
    fireEvent.change(textarea, { target: { value: 'Đi cafe sáng' } });
    fireEvent.click(screen.getByRole('button', { name: /Phối Đồ/i }));

    await waitFor(() => {
      expect(screen.getByRole('region', { name: /Khảo sát đánh giá gợi ý phối đồ/i })).toBeDefined();
    });

    const prompt = screen.getByRole('region', { name: /Khảo sát đánh giá gợi ý phối đồ/i });
    // Rate 5 stars via prompt
    const promptStar5Btn = within(prompt).getByRole('button', { name: 'Đánh giá 5 sao' });
    fireEvent.click(promptStar5Btn);

    await waitFor(() => {
      expect(rateSpy).toHaveBeenCalledWith('outfit-persisted-1', expect.objectContaining({
        stars: 5,
        source: 'prompted',
      }));
    });

    // Prompt shows thank you message before closing
    await waitFor(() => {
      expect(within(prompt).getByText('Cảm ơn bạn đã phản hồi!')).toBeDefined();
    });

    // After auto-dismiss timer (1500ms), prompt closes and OutfitCard reflects 5/5★
    await waitFor(
      () => {
        expect(screen.queryByRole('region', { name: /Khảo sát đánh giá gợi ý phối đồ/i })).toBeNull();
        expect(screen.getByText('5/5★')).toBeDefined();
      },
      { timeout: 3000 }
    );
  });

  it('does NOT render RatingPrompt if feedback_prompt_eligible is false or target outfit is not found', async () => {
    vi.spyOn(apiModule, 'sendStylistChat').mockResolvedValueOnce({
      ...mockSuccessData,
      feedback_prompt_eligible: true,
      feedback_target_outfit_id: 'non-existent-outfit-id',
    });

    render(<ChatPage />);

    const textarea = screen.getByLabelText(/Nhu cầu phối đồ của bạn/i);
    fireEvent.change(textarea, { target: { value: 'Đi dạo phố' } });
    fireEvent.click(screen.getByRole('button', { name: /Phối Đồ/i }));

    await waitFor(() => {
      expect(screen.getByText(/Gợi Ý Phối Đồ Số 1/i)).toBeDefined();
    });

    expect(screen.queryByRole('region', { name: /Khảo sát đánh giá gợi ý phối đồ/i })).toBeNull();
  });
});

