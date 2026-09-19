import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  ApiError,
  getStoredUserId,
  setStoredUserId,
  getStoredSessionId,
  setStoredSessionId,
  sendStylistChat,
  getOutfitDetail,
  getSavedOutfits,
  setOutfitBookmark,
  recordOutfitWorn,
  rateOutfit,
  dismissFeedbackPrompt,
  getMediaUrl,
  isSessionFeedbackSuppressed,
  clearMemorySuppressedSessionsForTesting,
  createTryOn,
} from '@/lib/api';
import type {
  OutfitDetailResponseData,
  SavedOutfitsResponseData,
  BookmarkResponseData,
  OutfitWornResponseData,
  OutfitRatingResponseData,
} from '@/types/outfits';
import type {
  StylistChatResponseData,
} from '@/types/chat';

describe('API Client & Storage Utilities (Contract & Invariant Verification)', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    clearMemorySuppressedSessionsForTesting();
    setStoredUserId('test-user-uuid-1234');
    setStoredSessionId('test-session-uuid-5678');
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  describe('Storage Helpers & Resilience', () => {
    it('stores and retrieves user ID from localStorage', () => {
      setStoredUserId('custom-user-id');
      expect(getStoredUserId()).toBe('custom-user-id');
      expect(localStorage.getItem('fashion_stylist_user_id')).toBe('custom-user-id');
    });

    it('generates a new user ID if none exists in localStorage', () => {
      localStorage.clear();
      const generated = getStoredUserId();
      expect(generated).toBeDefined();
      expect(typeof generated).toBe('string');
      expect(localStorage.getItem('fashion_stylist_user_id')).toBe(generated);
    });

    it('stores and retrieves session ID from sessionStorage', () => {
      setStoredSessionId('custom-session-id');
      expect(getStoredSessionId()).toBe('custom-session-id');
      expect(sessionStorage.getItem('fashion_stylist_session_id')).toBe('custom-session-id');
    });

    it('generates a new session ID if none exists in sessionStorage', () => {
      sessionStorage.clear();
      const generated = getStoredSessionId();
      expect(generated).toBeDefined();
      expect(typeof generated).toBe('string');
      expect(sessionStorage.getItem('fashion_stylist_session_id')).toBe(generated);
    });

    it('falls back gracefully without crashing when localStorage throws SecurityError (e.g. Private Browsing)', () => {
      vi.spyOn(Storage.prototype, 'getItem').mockImplementationOnce(() => {
        throw new Error('SecurityError: The operation is insecure.');
      });
      const fallbackId = getStoredUserId();
      expect(fallbackId).toBeDefined();
      expect(typeof fallbackId).toBe('string');
    });

    it('falls back gracefully without crashing when sessionStorage throws SecurityError', () => {
      vi.spyOn(Storage.prototype, 'getItem').mockImplementationOnce(() => {
        throw new Error('SecurityError: The operation is insecure.');
      });
      const fallbackId = getStoredSessionId();
      expect(fallbackId).toBeDefined();
      expect(typeof fallbackId).toBe('string');
    });
  });

  describe('ApiError Class', () => {
    it('instantiates correctly with code, status, message, and details', () => {
      const err = new ApiError('Lỗi xác thực', 'VALIDATION_ERROR', 422, { field: 'query' });
      expect(err).toBeInstanceOf(Error);
      expect(err).toBeInstanceOf(ApiError);
      expect(err.name).toBe('ApiError');
      expect(err.message).toBe('Lỗi xác thực');
      expect(err.code).toBe('VALIDATION_ERROR');
      expect(err.status).toBe(422);
      expect(err.details).toEqual({ field: 'query' });
    });
  });

  describe('Media URL Builder', () => {
    it('returns clean media URL without user_id query parameter leak', () => {
      const url = getMediaUrl('/api/v1/media/asset-123');
      expect(url).toBe('http://localhost:8000/api/v1/media/asset-123');
      expect(url).not.toContain('user_id');
    });

    it('returns absolute URLs untouched', () => {
      expect(getMediaUrl('https://example.com/photo.jpg')).toBe('https://example.com/photo.jpg');
    });
  });

  describe('Outfit Actions & Stylist Chat Endpoints (Strict Contract Matching)', () => {
    it('sendStylistChat calls POST /api/v1/stylist/chat with correct headers, body and receives matched response', async () => {
      const mockResponseData: StylistChatResponseData = {
        request_id: 'req-1',
        needs_clarification: false,
        clarification_question: null,
        context: {
          occasion: 'cafe',
          time_of_day: 'evening',
          event_date: null,
          location_text: 'Đà Lạt',
          environment: 'outdoor',
          weather_condition: 'cold',
          temperature_celsius: 15,
          target_formality_range: [2, 3],
          style_hints: ['smart_casual'],
          vibe_keywords: ['lịch sự nhẹ'],
          must_have: [],
          must_avoid: [],
          weather_source: 'user',
        },
        recommendations: [
          {
            outfit_id: 'persisted-uuid-1',
            rank: 1,
            composite_score: 0.91,
            items: [
              {
                slot: 'top',
                item_id: 'item-1',
                name: 'Áo polo trắng',
                image_url: '/api/v1/media/asset-1',
              },
            ],
            explanation_vi: 'Set đồ phù hợp với không khí se lạnh.',
            applied_preferences: ['smart casual'],
          },
        ],
        feedback_prompt_eligible: false,
        feedback_target_outfit_id: null,
        warnings: [],
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: mockResponseData }),
      } as Response);

      const result = await sendStylistChat({ query: 'Đi làm công sở', location: 'Hà Nội' });
      expect(result).toEqual(mockResponseData);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/stylist/chat'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'X-User-Id': 'test-user-uuid-1234',
            'X-Client-Session-Id': 'test-session-uuid-5678',
          }),
          body: JSON.stringify({
            query: 'Đi làm công sở',
            location: 'Hà Nội',
            client_session_id: 'test-session-uuid-5678',
          }),
        })
      );
    });

    it('getOutfitDetail calls GET /api/v1/outfits/{id} and returns full item details per contract', async () => {
      const mockDetail: OutfitDetailResponseData = {
        id: 'outfit-abc',
        request_id: 'req-abc',
        user_query: 'Đi chơi',
        explanation_vi: 'Đẹp',
        fashion_score: 0.9,
        personalization_score: 0.9,
        composite_score: 0.9,
        rank: 1,
        is_bookmarked: false,
        created_at: '2026-09-15T12:00:00Z',
        times_worn: 0,
        last_worn_at: null,
        user_rating: null,
        items: [
          {
            slot_role: 'top',
            wardrobe_item_id: 'item-top-1',
            name: 'Áo polo',
            category: 'top',
            sub_category: 'polo',
            primary_color: 'white',
            secondary_color: null,
            pattern: 'solid',
            material: 'cotton',
            style: 'smart_casual',
            image_url: '/api/v1/media/top-1',
            is_active: true,
          },
        ],
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: mockDetail }),
      } as Response);

      const result = await getOutfitDetail('outfit-abc');
      expect(result).toEqual(mockDetail);
      expect(result.id).toBe('outfit-abc');
      expect(result.items[0].wardrobe_item_id).toBe('item-top-1');
      expect(result.items[0].name).toBe('Áo polo');
      expect(result.items[0].is_active).toBe(true);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/outfits/outfit-abc'),
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({
            'X-User-Id': 'test-user-uuid-1234',
          }),
        })
      );
    });

    it('getSavedOutfits formats pagination parameters page and page_size in query string per contract', async () => {
      const mockSaved: SavedOutfitsResponseData = {
        items: [],
        total: 0,
        page: 2,
        page_size: 15,
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: mockSaved }),
      } as Response);

      const result = await getSavedOutfits({ page: 2, page_size: 15 });
      expect(result).toEqual(mockSaved);
      expect(Array.isArray(result.items)).toBe(true);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/outfits/saved?page=2&page_size=15'),
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({
            'X-User-Id': 'test-user-uuid-1234',
          }),
        })
      );
    });

    it('setOutfitBookmark calls PUT /api/v1/outfits/{id}/bookmark per API contract', async () => {
      const mockBookmark: BookmarkResponseData = {
        outfit_id: 'outfit-1',
        is_bookmarked: true,
        updated_at: '2026-09-15T12:00:00Z',
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: mockBookmark }),
      } as Response);

      const result = await setOutfitBookmark('outfit-1', true);
      expect(result).toEqual(mockBookmark);
      expect(result.updated_at).toBe('2026-09-15T12:00:00Z');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/outfits/outfit-1/bookmark'),
        expect.objectContaining({
          method: 'PUT',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'X-User-Id': 'test-user-uuid-1234',
          }),
          body: JSON.stringify({ is_bookmarked: true }),
        })
      );
    });

    it('recordOutfitWorn calls POST /api/v1/outfits/{id}/worn with optional worn_at and idempotency handling', async () => {
      const mockWorn: OutfitWornResponseData = {
        wear_log_id: 'log-1',
        outfit_id: 'outfit-1',
        worn_at: '2026-09-15T10:00:00Z',
        times_worn: 1,
        already_processed: true,
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: mockWorn }),
      } as Response);

      const payload = {
        idempotency_key: '550e8400-e29b-41d4-a716-446655440000',
      };
      const result = await recordOutfitWorn('outfit-1', payload);
      expect(result).toEqual(mockWorn);
      expect(result.already_processed).toBe(true);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/outfits/outfit-1/worn'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'X-User-Id': 'test-user-uuid-1234',
          }),
          body: JSON.stringify(payload),
        })
      );
    });

    it('rateOutfit with source=prompted automatically attaches X-Client-Session-Id and body', async () => {
      const mockRating: OutfitRatingResponseData = {
        rating_id: 'rate-1',
        outfit_id: 'outfit-1',
        stars: 5,
        source: 'prompted',
        ratings_count: 1,
        created_at: '2026-09-15T10:00:00Z',
        updated_at: '2026-09-15T10:00:00Z',
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: mockRating }),
      } as Response);

      const payload = {
        stars: 5,
        source: 'prompted' as const,
      };
      const result = await rateOutfit('outfit-1', payload);
      expect(result).toEqual(mockRating);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/outfits/outfit-1/rating'),
        expect.objectContaining({
          method: 'PUT',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'X-User-Id': 'test-user-uuid-1234',
            'X-Client-Session-Id': 'test-session-uuid-5678',
          }),
          body: JSON.stringify({
            stars: 5,
            source: 'prompted',
            client_session_id: 'test-session-uuid-5678',
          }),
        })
      );
    });

    it('rateOutfit with source=manual attaches the current session and suppresses later prompts', async () => {
      const mockRating: OutfitRatingResponseData = {
        rating_id: 'rate-2',
        outfit_id: 'outfit-1',
        stars: 4,
        source: 'manual',
        ratings_count: 1,
        created_at: '2026-09-15T10:00:00Z',
        updated_at: '2026-09-15T10:00:00Z',
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: mockRating }),
      } as Response);

      const payload = {
        stars: 4,
        source: 'manual' as const,
      };
      const result = await rateOutfit('outfit-1', payload);
      expect(result).toEqual(mockRating);

      // Every successful rating belongs to the active browser session.
      const callArgs = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const headers = callArgs[1].headers;
      expect(headers['X-Client-Session-Id']).toBe('test-session-uuid-5678');

      const body = JSON.parse(callArgs[1].body);
      expect(body.client_session_id).toBe('test-session-uuid-5678');
      expect(body.source).toBe('manual');
      expect(body.stars).toBe(4);
      expect(isSessionFeedbackSuppressed()).toBe(true);
    });

    it('dismissFeedbackPrompt calls POST /api/v1/feedback/prompts/dismiss with session ID', async () => {
      const mockDismiss = {
        cooldown_remaining: 3,
        dismissed: true,
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: mockDismiss }),
      } as Response);

      const result = await dismissFeedbackPrompt();
      expect(result).toEqual(mockDismiss);
      expect(isSessionFeedbackSuppressed()).toBe(false);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/feedback/prompts/dismiss'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'X-User-Id': 'test-user-uuid-1234',
            'X-Client-Session-Id': 'test-session-uuid-5678',
          }),
          body: JSON.stringify({
            client_session_id: 'test-session-uuid-5678',
          }),
        })
      );
    });

    it('createTryOn calls POST /api/v1/tryons with the persisted outfit ID', async () => {
      const mockTryOn = {
        tryon_id: 'tryon-1',
        outfit_id: 'outfit-1',
        image_url: '/api/v1/media/render-1',
        render_kind: 'moodboard' as const,
        fallback_used: true,
        duration_ms: 42,
        status: 'ready' as const,
      };
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: mockTryOn }),
      } as Response);

      await expect(createTryOn('outfit-1')).resolves.toEqual(mockTryOn);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/tryons'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'X-User-Id': 'test-user-uuid-1234',
          }),
          body: JSON.stringify({ outfit_id: 'outfit-1' }),
        })
      );
    });
  });

  describe('Error Envelope & Network Failure Handling', () => {
    it('throws ApiError with status, code, and message when backend returns an error envelope', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({
          error: {
            code: 'VALIDATION_ERROR',
            message: 'Dữ liệu không hợp lệ. Vui lòng kiểm tra lại.',
            details: { field: 'stars' },
          },
        }),
      } as Response);

      await expect(rateOutfit('outfit-1', { stars: 6, source: 'manual' })).rejects.toThrow(ApiError);

      try {
        await rateOutfit('outfit-1', { stars: 6, source: 'manual' });
      } catch (e) {
        const err = e as ApiError;
        expect(err.status).toBe(422);
        expect(err.code).toBe('VALIDATION_ERROR');
        expect(err.message).toBe('Dữ liệu không hợp lệ. Vui lòng kiểm tra lại.');
        expect(err.details).toEqual({ field: 'stars' });
      }
    });

    it('throws ApiError with INVALID_RESPONSE when response is not valid JSON', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => {
          throw new Error('Unexpected token < in JSON at position 0');
        },
      } as unknown as Response);

      await expect(getOutfitDetail('outfit-1')).rejects.toThrow(ApiError);

      try {
        await getOutfitDetail('outfit-1');
      } catch (e) {
        const err = e as ApiError;
        expect(err.status).toBe(502);
        expect(err.code).toBe('INVALID_RESPONSE');
        expect(err.message).toBe('Máy chủ trả về phản hồi không hợp lệ.');
      }
    });

    it('catches network dropout / connection reset and wraps into ApiError with NETWORK_ERROR code', async () => {
      global.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));

      await expect(getOutfitDetail('outfit-1')).rejects.toThrow(ApiError);

      try {
        await getOutfitDetail('outfit-1');
      } catch (e) {
        const err = e as ApiError;
        expect(err.status).toBe(0);
        expect(err.code).toBe('NETWORK_ERROR');
        expect(err.message).toContain('Không thể kết nối đến máy chủ');
      }
    });
  });
});
