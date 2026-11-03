'use client';

import { useRef, useState } from 'react';
import type { BoundingBox } from '@/types/ingestion';
import { PrivateMediaImage } from '@/components/media/PrivateMediaImage';

export function CropEditor({ source, initialBox, rawBox, onSave }: {
  source: string;
  initialBox: BoundingBox;
  rawBox?: BoundingBox | null;
  onSave: (box: BoundingBox) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [box, setBox] = useState<BoundingBox>(initialBox);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const start = useRef<[number, number] | null>(null);
  const valid = box[0] < box[2] && box[1] < box[3];

  return (
    <div className="mb-4 space-y-3">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}
        className="rounded-lg border px-4 py-2 text-sm">Chỉnh vùng cắt</button>
      {open && <>
        <p className="text-sm text-[#5C564E]">Kéo trên ảnh để chọn vùng mới hoặc điều chỉnh các cạnh bên dưới.</p>
        <div className="relative inline-block touch-none select-none"
          onPointerDown={(event) => {
            const rect = event.currentTarget.getBoundingClientRect();
            start.current = [(event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height];
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerCancel={() => { start.current = null; }}
          onPointerUp={(event) => {
            if (!start.current) return;
            const rect = event.currentTarget.getBoundingClientRect();
            const x = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
            const y = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
            const [sx, sy] = start.current;
            start.current = null;
            if (Math.abs(x - sx) > .01 && Math.abs(y - sy) > .01)
              setBox([Math.min(sx, x), Math.min(sy, y), Math.max(sx, x), Math.max(sy, y)]);
          }}>
          <PrivateMediaImage source={source} alt="Ảnh gốc để chỉnh vùng cắt"
            draggable={false} className="block max-h-80 max-w-full" />
          <div className="pointer-events-none absolute border-2 border-[#9C5234] bg-[#9C5234]/15"
            style={{ left: `${box[0] * 100}%`, top: `${box[1] * 100}%`,
              width: `${(box[2] - box[0]) * 100}%`, height: `${(box[3] - box[1]) * 100}%` }} />
        </div>
        {['Cạnh trái', 'Cạnh trên', 'Cạnh phải', 'Cạnh dưới'].map((label, index) => (
          <label key={label} className="flex items-center gap-3 text-sm">
            <span className="w-20">{label}</span>
            <input type="range" min={0} max={100} step={1} value={Math.round(box[index] * 100)}
              onChange={(event) => setBox(box.map((value, i) => i === index ? Number(event.target.value) / 100 : value) as BoundingBox)} />
            <span>{Math.round(box[index] * 100)}%</span>
          </label>
        ))}
        {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
        <div className="flex flex-wrap gap-2">
          {rawBox && <button type="button" onClick={() => setBox([...rawBox])} disabled={saving}
            className="rounded-lg border px-3 py-2 text-sm">Khung AI gốc</button>}
          <button type="button" onClick={() => setBox(initialBox)} disabled={saving} className="rounded-lg border px-3 py-2 text-sm">Đặt lại</button>
          <button type="button" onClick={() => setBox([0, 0, 1, 1])} disabled={saving} className="rounded-lg border px-3 py-2 text-sm">Lấy toàn ảnh</button>
          <button type="button" disabled={!valid || saving} className="rounded-lg bg-[#9C5234] px-3 py-2 text-sm text-white disabled:opacity-50"
            onClick={async () => {
              setSaving(true); setError(null);
              try { await onSave(box); setOpen(false); }
              catch (reason) { setError(reason instanceof Error ? reason.message : 'Không thể lưu vùng cắt.'); }
              finally { setSaving(false); }
            }}>{saving ? 'Đang lưu…' : 'Lưu vùng cắt'}</button>
        </div>
      </>}
    </div>
  );
}
