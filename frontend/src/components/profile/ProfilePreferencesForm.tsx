'use client';

import { useEffect, useState, useRef } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import {
  getPreferenceOptions,
  getUserProfile,
  replaceUserPreferences,
} from '@/lib/api';
import type {
  PreferenceOptionGroup,
  PreferenceOptions,
  PreferenceSelections,
} from '@/types/profile';

const EMPTY_PREFERENCES: PreferenceSelections = {
  styles: [],
  color_palettes: [],
  priorities: [],
  avoid_colors: [],
  avoid_styles: [],
  fit_preferences: [],
};

const LABELS: Record<string, string> = {
  casual: 'Thoải mái', minimalist: 'Tối giản', smart_casual: 'Thanh lịch thường ngày',
  streetwear: 'Đường phố', formal: 'Trang trọng', vintage: 'Cổ điển', neutral: 'Trung tính',
  earth_tone: 'Tông đất', cool_tone: 'Tông lạnh', warm_tone: 'Tông ấm',
  monochrome: 'Đơn sắc', comfort: 'Thoải mái', polished: 'Chỉn chu', expressive: 'Nổi bật',
  mobility: 'Dễ vận động', low_maintenance: 'Dễ chăm sóc', slim: 'Ôm', regular: 'Vừa vặn',
  relaxed: 'Rộng vừa', oversized: 'Rộng', white: 'Trắng', black: 'Đen', grey: 'Xám',
  beige: 'Be', cream: 'Kem', khaki: 'Khaki', navy: 'Xanh navy', brown: 'Nâu', tan: 'Nâu nhạt',
  red: 'Đỏ', orange: 'Cam', yellow: 'Vàng', green: 'Xanh lá', blue: 'Xanh dương',
  purple: 'Tím', pink: 'Hồng',
};

interface OptionSectionProps {
  title: string;
  description: string;
  group: PreferenceOptionGroup;
  selected: string[];
  onChange: (values: string[]) => void;
}

function OptionSection({ title, description, group, selected, onChange }: OptionSectionProps) {
  const toggle = (value: string) => {
    if (selected.includes(value)) {
      onChange(selected.filter((item) => item !== value));
    } else if (selected.length < group.selection_limit) {
      onChange([...selected, value]);
    }
  };

  return (
    <fieldset className="space-y-3">
      <legend className="font-serif text-lg font-medium text-[#1A1918]">{title}</legend>
      <p className="text-xs text-[#736E65]">{description}</p>
      <div className="flex flex-wrap gap-2">
        {group.values.map((value) => {
          const active = selected.includes(value);
          return (
            <button
              key={value}
              type="button"
              onClick={() => toggle(value)}
              className={`tactile-btn rounded-full px-4 py-2 text-xs font-medium transition ${
                active
                  ? 'bg-[#1A1918] text-[#FBFBF9] shadow-xs'
                  : 'bg-white text-[#5C564E] border border-[#E8E5DE] hover:border-[#D5D1C7] hover:text-[#1A1918]'
              }`}
            >
              {LABELS[value] || value}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

export function ProfilePreferencesForm() {
  const router = useRouter();
  const [options, setOptions] = useState<PreferenceOptions | null>(null);
  const [preferences, setPreferences] = useState<PreferenceSelections>(EMPTY_PREFERENCES);
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'saved'>('loading');
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const redirectTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    Promise.all([getPreferenceOptions(), getUserProfile()])
      .then(([loadedOptions, profile]) => {
        setOptions(loadedOptions);
        setPreferences(profile.preferences);
        setStatus('ready');
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : 'Không thể tải hồ sơ lúc này.');
        setStatus('ready');
      });

    return () => {
      if (redirectTimerRef.current) {
        clearTimeout(redirectTimerRef.current);
      }
    };
  }, []);

  const update = (field: keyof PreferenceSelections, values: string[]) => {
    setPreferences((current) => ({ ...current, [field]: values }));
    setStatus('ready');
    setSuccessMessage(null);
  };

  const save = async (nextPreferences = preferences, isSkip = false) => {
    setStatus('saving');
    setError(null);
    setSuccessMessage(null);
    try {
      const profile = await replaceUserPreferences(nextPreferences);
      setPreferences(profile.preferences);
      setStatus('saved');

      if (isSkip) {
        setSuccessMessage('Đã bỏ qua thiết lập sở thích. Đang chuyển tiếp sang tủ đồ...');
        redirectTimerRef.current = setTimeout(() => {
          router.push('/wardrobe');
        }, 1200);
      } else {
        setSuccessMessage('Đã lưu sở thích thành công!');
      }
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : isSkip
          ? 'Không thể bỏ qua lúc này.'
          : 'Không thể lưu hồ sơ lúc này.'
      );
      setStatus('ready');
    }
  };

  if (status === 'loading') {
    return <p className="text-slate-300" role="status">Đang tải lựa chọn phong cách...</p>;
  }
  if (!options) {
    return <p className="text-rose-300" role="alert">{error}</p>;
  }

  return (
    <form
      className="space-y-9"
      onSubmit={(event) => {
        event.preventDefault();
        void save(preferences, false);
      }}
    >
      <OptionSection
        title="Phong cách"
        description="Chọn tối đa 3 phong cách bạn thường mặc."
        group={options.styles}
        selected={preferences.styles}
        onChange={(v) => update('styles', v)}
      />
      <OptionSection
        title="Bảng màu"
        description="Chọn tối đa 3 nhóm màu bạn yêu thích."
        group={options.color_palettes}
        selected={preferences.color_palettes}
        onChange={(v) => update('color_palettes', v)}
      />
      <OptionSection
        title="Ưu tiên"
        description="Điều gì quan trọng nhất khi phối đồ?"
        group={options.priorities}
        selected={preferences.priorities}
        onChange={(v) => update('priorities', v)}
      />
      <OptionSection
        title="Phom dáng"
        description="Bạn có thể chọn một phom dáng hoặc bỏ qua."
        group={options.fit_preferences}
        selected={preferences.fit_preferences}
        onChange={(v) => update('fit_preferences', v)}
      />
      <OptionSection
        title="Màu muốn tránh"
        description="Các màu này sẽ được ưu tiên loại khỏi gợi ý."
        group={options.avoid_colors}
        selected={preferences.avoid_colors}
        onChange={(v) => update('avoid_colors', v)}
      />
      <OptionSection
        title="Phong cách muốn tránh"
        description="Chọn những phong cách không phù hợp với bạn."
        group={options.avoid_styles}
        selected={preferences.avoid_styles}
        onChange={(v) => update('avoid_styles', v)}
      />

      {error && (
        <p className="text-sm text-rose-300" role="alert">
          {error}
        </p>
      )}

      {successMessage && (
        <div
          role="status"
          className="flex items-center justify-between flex-wrap gap-3 rounded-2xl bg-white border border-[#E8E5DE] px-5 py-4 text-[#1A1918] text-sm shadow-xs animate-fadeIn"
        >
          <span className="font-medium">✓ {successMessage}</span>
          <div className="flex items-center gap-3 text-xs font-mono uppercase tracking-wider">
            <Link
              href="/wardrobe"
              className="text-[#9C5234] hover:underline"
            >
              Sang Tủ Đồ →
            </Link>
            <span className="text-[#D5D1C7]">|</span>
            <Link
              href="/chat"
              className="text-[#9C5234] hover:underline"
            >
              Tư Vấn Stylist →
            </Link>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-3 pt-4 border-t border-[#E8E5DE]">
        <button
          type="submit"
          disabled={status === 'saving'}
          className="tactile-btn rounded-full bg-[#1A1918] px-6 py-3 font-mono text-xs uppercase tracking-wider text-[#FBFBF9] hover:bg-[#2D2420] transition disabled:opacity-50 shadow-xs"
        >
          {status === 'saving' ? 'Đang lưu...' : 'Lưu sở thích'}
        </button>
        <button
          type="button"
          disabled={status === 'saving'}
          onClick={() => {
            setPreferences(EMPTY_PREFERENCES);
            void save(EMPTY_PREFERENCES, true);
          }}
          className="tactile-btn rounded-full border border-[#D5D1C7] bg-white px-6 py-3 font-mono text-xs uppercase tracking-wider text-[#736E65] hover:text-[#1A1918] hover:bg-[#F5F4F0] transition disabled:opacity-50"
        >
          Bỏ qua onboarding
        </button>
      </div>
    </form>
  );
}
