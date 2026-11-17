'use client';

import { useEffect, useState, useRef } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import { getPreferenceOptions, getUserProfile, replaceUserPreferences } from '@/lib/api';
import { preferenceLabel } from '@/lib/preferenceLabels';
import { CheckIcon, Spinner } from '@/components/ui/icons';
import type { PreferenceOptionGroup, PreferenceOptions, PreferenceSelections } from '@/types/profile';

const EMPTY_PREFERENCES: PreferenceSelections = {
  styles: [],
  color_palettes: [],
  priorities: [],
  avoid_colors: [],
  avoid_styles: [],
  fit_preferences: [],
};

function hasAnySelection(preferences: PreferenceSelections): boolean {
  return Object.values(preferences).some((values) => values.length > 0);
}

interface OptionSectionProps {
  title: string;
  description: string;
  group: PreferenceOptionGroup;
  selected: string[];
  onChange: (values: string[]) => void;
}

function OptionSection({ title, description, group, selected, onChange }: OptionSectionProps) {
  const atLimit = selected.length >= group.selection_limit;

  const toggle = (value: string) => {
    if (selected.includes(value)) {
      onChange(selected.filter((item) => item !== value));
    } else if (!atLimit) {
      onChange([...selected, value]);
    }
  };

  return (
    <fieldset className="border-t border-line pt-6 first:border-t-0 first:pt-0">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <legend className="display text-xl">{title}</legend>
        {/* Only meaningful when the limit is tight (e.g. "up to 3 styles"). */}
        {group.selection_limit <= 5 && (
          <span className={`text-xs tabular-nums ${atLimit ? 'font-semibold text-accent' : 'text-muted'}`}>
            {selected.length}/{group.selection_limit}
          </span>
        )}
      </div>
      <p className="mb-3 text-sm text-muted">{description}</p>
      <div className="flex flex-wrap gap-2">
        {group.values.map((value) => {
          const active = selected.includes(value);
          return (
            <button
              key={value}
              type="button"
              aria-pressed={active}
              disabled={!active && atLimit}
              onClick={() => toggle(value)}
              className="chip"
            >
              {preferenceLabel(value)}
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
  const [isFirstSetup, setIsFirstSetup] = useState(false);
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'saved'>('loading');
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const redirectTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    Promise.all([getPreferenceOptions(), getUserProfile()])
      .then(([loadedOptions, profile]) => {
        setOptions(loadedOptions);
        setPreferences(profile.preferences);
        setIsFirstSetup(!hasAnySelection(profile.preferences));
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
        setSuccessMessage('Đã bỏ qua. Bạn có thể quay lại chọn gu bất cứ lúc nào.');
        redirectTimerRef.current = setTimeout(() => {
          router.push('/wardrobe');
        }, 1200);
      } else {
        setIsFirstSetup(false);
        setSuccessMessage('Đã lưu gu của bạn.');
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
    return (
      <p className="flex items-center gap-2 text-sm text-muted" role="status">
        <Spinner size={16} />
        Đang tải lựa chọn phong cách…
      </p>
    );
  }
  if (!options) {
    return (
      <p className="notice notice-danger" role="alert">
        {error}
      </p>
    );
  }

  return (
    <form
      className="card space-y-6 p-5 sm:p-7"
      onSubmit={(event) => {
        event.preventDefault();
        void save(preferences, false);
      }}
    >
      <OptionSection
        title="Phong cách"
        description="Những phong cách bạn hay mặc."
        group={options.styles}
        selected={preferences.styles}
        onChange={(v) => update('styles', v)}
      />
      <OptionSection
        title="Bảng màu"
        description="Nhóm màu bạn thấy hợp với mình."
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
        description="Độ ôm bạn thấy dễ chịu nhất."
        group={options.fit_preferences}
        selected={preferences.fit_preferences}
        onChange={(v) => update('fit_preferences', v)}
      />
      <OptionSection
        title="Màu muốn tránh"
        description="Những màu này sẽ ít xuất hiện trong gợi ý."
        group={options.avoid_colors}
        selected={preferences.avoid_colors}
        onChange={(v) => update('avoid_colors', v)}
      />
      <OptionSection
        title="Phong cách muốn tránh"
        description="Những phong cách không dành cho bạn."
        group={options.avoid_styles}
        selected={preferences.avoid_styles}
        onChange={(v) => update('avoid_styles', v)}
      />

      {error && (
        <p className="notice notice-danger" role="alert">
          {error}
        </p>
      )}

      {successMessage && (
        <div role="status" className="notice notice-success animate-rise flex-wrap items-center justify-between">
          <span className="flex items-center gap-2 font-semibold">
            <CheckIcon size={16} />
            {successMessage}
          </span>
          {status === 'saved' && !isFirstSetup && (
            <Link href="/chat" className="font-semibold underline-offset-4 hover:underline">
              Thử phối đồ ngay
            </Link>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 border-t border-line pt-6">
        <button type="submit" disabled={status === 'saving'} className="btn btn-primary">
          {status === 'saving' ? 'Đang lưu…' : 'Lưu gu của tôi'}
        </button>
        {isFirstSetup && (
          <button
            type="button"
            disabled={status === 'saving'}
            onClick={() => {
              setPreferences(EMPTY_PREFERENCES);
              void save(EMPTY_PREFERENCES, true);
            }}
            className="btn btn-ghost"
          >
            Bỏ qua, để sau
          </button>
        )}
      </div>
    </form>
  );
}
