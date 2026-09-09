'use client';

import { useEffect, useState } from 'react';

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
      <legend className="text-lg font-semibold text-slate-100">{title}</legend>
      <p className="text-sm text-slate-400">{description}</p>
      <div className="flex flex-wrap gap-2">
        {group.values.map((value) => {
          const active = selected.includes(value);
          const disabled = !active && selected.length >= group.selection_limit;
          return (
            <button
              key={value}
              type="button"
              aria-pressed={active}
              disabled={disabled}
              onClick={() => toggle(value)}
              className={`rounded-full border px-4 py-2 text-sm transition ${
                active
                  ? 'border-indigo-400 bg-indigo-500/25 text-indigo-100'
                  : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-500'
              } disabled:cursor-not-allowed disabled:opacity-40`}
            >
              {LABELS[value] ?? value}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

export function ProfilePreferencesForm() {
  const [options, setOptions] = useState<PreferenceOptions | null>(null);
  const [preferences, setPreferences] = useState<PreferenceSelections>(EMPTY_PREFERENCES);
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'saved'>('loading');
  const [error, setError] = useState<string | null>(null);

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
  }, []);

  const update = (field: keyof PreferenceSelections, values: string[]) => {
    setPreferences((current) => ({ ...current, [field]: values }));
    setStatus('ready');
  };

  const save = async (nextPreferences = preferences) => {
    setStatus('saving');
    setError(null);
    try {
      const profile = await replaceUserPreferences(nextPreferences);
      setPreferences(profile.preferences);
      setStatus('saved');
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : 'Không thể lưu hồ sơ lúc này.');
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
    <form className="space-y-9" onSubmit={(event) => { event.preventDefault(); void save(); }}>
      <OptionSection title="Phong cách" description="Chọn tối đa 3 phong cách bạn thường mặc."
        group={options.styles} selected={preferences.styles} onChange={(v) => update('styles', v)} />
      <OptionSection title="Bảng màu" description="Chọn tối đa 3 nhóm màu bạn yêu thích."
        group={options.color_palettes} selected={preferences.color_palettes} onChange={(v) => update('color_palettes', v)} />
      <OptionSection title="Ưu tiên" description="Điều gì quan trọng nhất khi phối đồ?"
        group={options.priorities} selected={preferences.priorities} onChange={(v) => update('priorities', v)} />
      <OptionSection title="Phom dáng" description="Bạn có thể chọn một phom dáng hoặc bỏ qua."
        group={options.fit_preferences} selected={preferences.fit_preferences} onChange={(v) => update('fit_preferences', v)} />
      <OptionSection title="Màu muốn tránh" description="Các màu này sẽ được ưu tiên loại khỏi gợi ý."
        group={options.avoid_colors} selected={preferences.avoid_colors} onChange={(v) => update('avoid_colors', v)} />
      <OptionSection title="Phong cách muốn tránh" description="Chọn những phong cách không phù hợp với bạn."
        group={options.avoid_styles} selected={preferences.avoid_styles} onChange={(v) => update('avoid_styles', v)} />

      {error && <p className="text-sm text-rose-300" role="alert">{error}</p>}
      {status === 'saved' && <p className="text-sm text-emerald-300" role="status">Đã lưu sở thích.</p>}
      <div className="flex flex-wrap gap-3">
        <button type="submit" disabled={status === 'saving'}
          className="rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white hover:bg-indigo-500 disabled:opacity-50">
          {status === 'saving' ? 'Đang lưu...' : 'Lưu sở thích'}
        </button>
        <button type="button" disabled={status === 'saving'} onClick={() => { setPreferences(EMPTY_PREFERENCES); void save(EMPTY_PREFERENCES); }}
          className="rounded-xl border border-slate-700 px-5 py-3 font-semibold text-slate-300 hover:border-slate-500 disabled:opacity-50">
          Bỏ qua onboarding
        </button>
      </div>
    </form>
  );
}
