'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { WardrobeItem, WardrobeItemUpdatePayload } from '@/types/wardrobe';
import { deleteWardrobeItem, listWardrobeItems, updateWardrobeItem } from '@/lib/api';
import { useGarmentTaxonomy } from '@/lib/useGarmentTaxonomy';
import { PrivateMediaImage } from '@/components/media/PrivateMediaImage';
import { PageHeader } from '@/components/layout/AppShell';
import { attributeLabel } from '@/lib/preferenceLabels';
import { FUNCTIONAL_FLAG_VALUES, FUNCTION_TAG_NAMES, hasGarmentLength } from '@/lib/garmentAttributes';
import { SegmentedScale } from '@/components/ui/SegmentedScale';
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  CameraIcon,
  CheckIcon,
  CloseIcon,
  HangerIcon,
  PencilIcon,
  PlusIcon,
  SearchIcon,
  TrashIcon,
} from '@/components/ui/icons';

export const SILHOUETTE_NAMES: Record<number, string> = {
  1: 'Rất ôm sát',
  2: 'Ôm vừa',
  3: 'Tiêu chuẩn',
  4: 'Dáng rộng',
  5: 'Oversized',
};

export const LENGTH_NAMES: Record<string, string> = {
  cropped: 'Lửng (Cropped)',
  waist: 'Ngang eo',
  hip: 'Ngang hông',
  long: 'Dáng dài',
};

interface ScaleInputProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  lowLabel: string;
  highLabel: string;
  testIdPrefix?: string;
}

/** Labelled 1–5 scale with end-point captions. */
function ScaleInput({ label, value, onChange, lowLabel, highLabel, testIdPrefix }: ScaleInputProps) {
  return (
    <div>
      <span className="field-label">
        {label} <span className="font-normal text-muted">· {value}/5</span>
      </span>
      <SegmentedScale label={label} value={value} onChange={onChange} testIdPrefix={testIdPrefix} />
      <div className="mt-1 flex justify-between text-xs text-muted">
        <span>{lowLabel}</span>
        <span>{highLabel}</span>
      </div>
    </div>
  );
}

interface WardrobeInventoryProps {
  onSwitchToIngestion?: () => void;
  /** One-off confirmation shown after adding items. */
  notice?: string | null;
  onDismissNotice?: () => void;
  /** An unfinished upload exists in this browser session. */
  hasPendingBatch?: boolean;
}

export function WardrobeInventory({
  onSwitchToIngestion,
  notice,
  onDismissNotice,
  hasPendingBatch = false,
}: WardrobeInventoryProps) {
  const [items, setItems] = useState<WardrobeItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestSequence = useRef(0);

  const { taxonomy, taxonomyError, retryTaxonomy } = useGarmentTaxonomy();
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 12;

  // Edit dialog state
  const [editingItem, setEditingItem] = useState<WardrobeItem | null>(null);
  const [editForm, setEditForm] = useState<WardrobeItemUpdatePayload>({});
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Delete dialog state
  const [deletingItemId, setDeletingItemId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const fetchItems = useCallback(async () => {
    const requestId = ++requestSequence.current;
    setLoading(true);
    setError(null);
    try {
      const res = await listWardrobeItems({
        item_group: selectedCategory === 'all' ? undefined : selectedCategory,
        text: submittedQuery || undefined,
        page,
        page_size: pageSize,
      });
      if (requestId !== requestSequence.current) return;
      setItems(res.items);
      setTotal(res.total);
    } catch (err) {
      if (requestId === requestSequence.current) {
        setError(err instanceof Error ? err.message : 'Không thể tải danh sách trang phục.');
      }
    } finally {
      if (requestId === requestSequence.current) setLoading(false);
    }
  }, [selectedCategory, submittedQuery, page]);

  useEffect(() => {
    void Promise.resolve().then(fetchItems);
  }, [fetchItems]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setSubmittedQuery(searchQuery.trim());
  };

  const handleOpenEdit = (item: WardrobeItem) => {
    setEditingItem(item);
    setEditError(null);
    setEditForm({
      sub_category: item.sub_category,
      primary_color: item.primary_color,
      style: item.style,
      material: item.material,
      fit: item.fit,
      formality_level: item.formality_level,
      comfort_level: item.comfort_level ?? 3,
      silhouette_level: item.silhouette_level ?? 3,
      length: item.length || 'hip',
      functional_flags: item.functional_flags ? [...item.functional_flags] : [],
    });
  };

  const handleSaveEdit = async () => {
    if (!editingItem) return;
    setSavingEdit(true);
    setEditError(null);
    try {
      const updated = await updateWardrobeItem(editingItem.id, editForm);
      setItems((prev) => prev.map((it) => (it.id === updated.id ? updated : it)));
      setEditingItem(null);
    } catch (err) {
      setEditError(err instanceof Error ? err.message : 'Cập nhật trang phục thất bại.');
    } finally {
      setSavingEdit(false);
    }
  };

  const handleDelete = async (itemId: string) => {
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteWardrobeItem(itemId);
      setItems((prev) => prev.filter((it) => it.id !== itemId));
      setTotal((prev) => Math.max(0, prev - 1));
      setDeletingItemId(null);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'Xóa trang phục thất bại.');
    } finally {
      setDeleting(false);
    }
  };

  // Dialogs stay open while a request is in flight so its outcome (especially an error) is never lost.
  const closeEdit = () => {
    if (!savingEdit) setEditingItem(null);
  };
  const closeDelete = () => {
    if (!deleting) setDeletingItemId(null);
  };

  const totalPages = Math.ceil(total / pageSize);
  const isFiltered = Boolean(submittedQuery) || selectedCategory !== 'all';
  const deletingItem = items.find((it) => it.id === deletingItemId);

  return (
    <div>
      <PageHeader
        title="Tủ đồ"
        description={loading && total === 0 ? 'Đang mở tủ đồ…' : `${total} món đồ sẵn sàng để phối.`}
        actions={
          onSwitchToIngestion && (
            <button
              type="button"
              data-testid="btn-add-garment"
              onClick={onSwitchToIngestion}
              className="btn btn-primary"
            >
              <PlusIcon size={16} />
              Thêm món đồ
            </button>
          )
        }
      />

      {notice && (
        <div role="status" className="notice notice-success mb-6 animate-rise items-center">
          <CheckIcon size={16} className="shrink-0" />
          <span className="flex-1 font-semibold">{notice}</span>
          {onDismissNotice && (
            <button type="button" onClick={onDismissNotice} aria-label="Đóng thông báo" className="-m-2 flex h-8 w-8 shrink-0 items-center justify-center rounded-full">
              <CloseIcon size={14} />
            </button>
          )}
        </div>
      )}

      {hasPendingBatch && onSwitchToIngestion && (
        <div className="notice notice-info mb-6 items-center">
          <CameraIcon size={16} className="shrink-0" />
          <span className="flex-1">Bạn còn một lượt thêm đồ chưa xong.</span>
          <button type="button" onClick={onSwitchToIngestion} className="btn btn-secondary btn-sm">
            Tiếp tục
          </button>
        </div>
      )}

      {/* Search + filters */}
      <div className="mb-6 space-y-3">
        <form onSubmit={handleSearchSubmit} className="flex max-w-xl gap-2" role="search">
          <div className="relative min-w-0 flex-1">
            <SearchIcon size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
            <input
              type="text"
              aria-label="Tìm kiếm trong tủ đồ"
              data-testid="wardrobe-search-input"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Tìm theo loại, màu, phong cách — ví dụ: giày đen"
              className="field pl-10"
            />
          </div>
          <button type="submit" className="btn btn-secondary">
            Tìm
          </button>
        </form>

        {taxonomyError && (
          <p role="alert" className="text-sm text-danger">
            Chưa tải được bộ lọc.{' '}
            <button type="button" onClick={retryTaxonomy} className="font-semibold underline">
              Thử lại
            </button>
          </p>
        )}

        <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:px-0" aria-label="Lọc theo loại">
          {[{ label: 'Tất cả', value: 'all' }, ...taxonomy.groups].map((cat) => (
            <button
              key={cat.value}
              type="button"
              aria-pressed={selectedCategory === cat.value}
              data-testid={`category-filter-${cat.value}`}
              onClick={() => {
                setSelectedCategory(cat.value);
                setPage(1);
              }}
              className="chip shrink-0"
            >
              {cat.label}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div data-testid="wardrobe-loading" role="status" className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          <span className="sr-only">Đang tải danh sách trang phục…</span>
          {Array.from({ length: 8 }).map((_, idx) => (
            <div key={idx} className="space-y-2">
              <div className="aspect-[4/5] animate-pulse rounded-2xl bg-sunken" />
              <div className="h-3 w-2/3 animate-pulse rounded bg-sunken" />
            </div>
          ))}
        </div>
      )}

      {error && !loading && <div className="notice notice-danger">{error}</div>}

      {!loading && !error && items.length === 0 && (
        <div className="card border-dashed px-6 py-14 text-center">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-sunken text-accent">
            <HangerIcon size={24} />
          </span>
          <h3 className="display mt-5 text-2xl">{isFiltered ? 'Không tìm thấy món nào' : 'Chưa có trang phục nào'}</h3>
          <p className="mx-auto mt-2 max-w-sm text-[0.9375rem] leading-relaxed text-ink-2">
            {isFiltered
              ? 'Thử từ khóa khác hoặc chọn “Tất cả”.'
              : 'Chụp ảnh vài món bạn hay mặc — áo, quần, giày — để bắt đầu nhận gợi ý phối đồ.'}
          </p>
          {onSwitchToIngestion && !isFiltered && (
            <button type="button" onClick={onSwitchToIngestion} className="btn btn-primary mt-6">
              <CameraIcon size={16} />
              Thêm món đồ đầu tiên
            </button>
          )}
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <ul className="grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 lg:grid-cols-4">
          {items.map((item) => {
            const name = item.display_name_vi || item.sub_category;
            const silhouette = item.silhouette_level ? SILHOUETTE_NAMES[item.silhouette_level] || `Dáng ${item.silhouette_level}` : '';
            const length = item.length && hasGarmentLength(item.category) ? LENGTH_NAMES[item.length] || item.length : '';
            return (
              <li key={item.id} data-testid={`wardrobe-item-card-${item.id}`} className="group relative min-w-0">
                <div className="relative flex aspect-[4/5] items-center justify-center overflow-hidden rounded-2xl bg-sunken">
                  {item.thumbnail_url || item.media_url ? (
                    <PrivateMediaImage
                      source={item.thumbnail_url || item.media_url || ''}
                      alt={name}
                      className="h-full w-full object-contain p-3 transition-transform duration-300 group-hover:scale-[1.03]"
                    />
                  ) : (
                    <HangerIcon size={32} className="text-line-strong" />
                  )}
                  <span className="hang-tag absolute left-2.5 top-2.5">{item.group_label_vi || 'Chưa phân loại'}</span>
                  {item.times_worn > 0 && (
                    <span className="absolute bottom-2.5 left-2.5 rounded-full bg-ink/80 px-2 py-0.5 text-[0.6875rem] font-semibold text-paper">
                      Mặc {item.times_worn} lần
                    </span>
                  )}
                  {/* Reveal-on-hover only where hover exists; touch screens always show the actions. */}
                  <div className="absolute right-2 top-2 flex gap-1 transition-opacity [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-focus-within:opacity-100 [@media(hover:hover)]:group-hover:opacity-100">
                    <button
                      type="button"
                      data-testid={`edit-item-${item.id}`}
                      onClick={() => handleOpenEdit(item)}
                      aria-label={`Chỉnh sửa ${name}`}
                      className="flex h-8 w-8 items-center justify-center rounded-full bg-surface/95 text-ink shadow-sm hover:bg-surface"
                    >
                      <PencilIcon size={15} />
                    </button>
                    <button
                      type="button"
                      data-testid={`delete-item-${item.id}`}
                      onClick={() => {
                        setDeleteError(null);
                        setDeletingItemId(item.id);
                      }}
                      aria-label={`Xóa ${name}`}
                      className="flex h-8 w-8 items-center justify-center rounded-full bg-surface/95 text-danger shadow-sm hover:bg-surface"
                    >
                      <TrashIcon size={15} />
                    </button>
                  </div>
                </div>

                <h4 className="mt-2.5 truncate text-[0.9375rem] font-semibold capitalize text-ink">{name}</h4>
                <p className="truncate text-sm text-muted first-letter:uppercase">
                  {[attributeLabel(item.primary_color), attributeLabel(item.style)].filter(Boolean).join(' · ')}
                </p>
                <div className="mt-1.5 flex flex-wrap gap-x-2 gap-y-0.5 text-xs text-ink-2">
                  <span>Trang trọng {item.formality_level}/5</span>
                  {item.comfort_level !== undefined && item.comfort_level !== null && (
                    <span data-testid={`badge-comfort-${item.id}`}>Thoải mái {item.comfort_level}/5</span>
                  )}
                  {(silhouette || length) && (
                    <span data-testid={`badge-silhouette-${item.id}`}>
                      {silhouette}
                      {silhouette && length ? ' · ' : ''}
                      {length}
                    </span>
                  )}
                </div>
                {item.functional_flags && item.functional_flags.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {item.functional_flags.map((flag) => (
                      <span key={flag} className="rounded bg-sunken px-1.5 py-0.5 text-[0.6875rem] text-muted">
                        {FUNCTION_TAG_NAMES[flag] || flag}
                      </span>
                    ))}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {totalPages > 1 && (
        <nav aria-label="Phân trang tủ đồ" className="mt-10 flex items-center justify-center gap-3">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="btn btn-secondary btn-sm"
          >
            <ArrowLeftIcon size={15} />
            Trước
          </button>
          <span className="text-sm tabular-nums text-muted">
            Trang {page} / {totalPages}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            className="btn btn-secondary btn-sm"
          >
            Sau
            <ArrowRightIcon size={15} />
          </button>
        </nav>
      )}

      {/* Edit dialog */}
      {editingItem && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 p-0 backdrop-blur-[2px] sm:items-center sm:p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeEdit();
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="edit-item-title"
            className="max-h-[92dvh] w-full max-w-lg overflow-y-auto rounded-t-3xl bg-surface shadow-2xl sm:rounded-3xl"
          >
            <div className="flex items-start justify-between gap-3 border-b border-line px-6 pb-4 pt-5">
              <div>
                <h3 id="edit-item-title" className="display text-2xl">
                  Chỉnh sửa món đồ
                </h3>
                <p className="mt-0.5 text-sm capitalize text-muted">
                  {editingItem.display_name_vi || editingItem.sub_category}
                </p>
              </div>
              <button
                type="button"
                onClick={closeEdit}
                disabled={savingEdit}
                aria-label="Đóng"
                className="btn btn-ghost btn-icon -mr-2"
              >
                <CloseIcon size={18} />
              </button>
            </div>

            <div className="space-y-5 px-6 py-5">
              <section className="space-y-3">
                <h4 className="text-sm font-semibold text-ink">Thông tin cơ bản</h4>
                <div>
                  <label htmlFor="edit-sub-category" className="field-label">
                    Tên / loại món
                  </label>
                  <input
                    id="edit-sub-category"
                    type="text"
                    data-testid="edit-sub-category"
                    value={editForm.sub_category || ''}
                    onChange={(e) => setEditForm((f) => ({ ...f, sub_category: e.target.value }))}
                    className="field"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label htmlFor="edit-primary-color" className="field-label">
                      Màu chính
                    </label>
                    <input
                      id="edit-primary-color"
                      type="text"
                      data-testid="edit-primary-color"
                      value={editForm.primary_color || ''}
                      onChange={(e) => setEditForm((f) => ({ ...f, primary_color: e.target.value }))}
                      className="field"
                    />
                  </div>
                  <div>
                    <label htmlFor="edit-style" className="field-label">
                      Phong cách
                    </label>
                    <input
                      id="edit-style"
                      type="text"
                      data-testid="edit-style"
                      value={editForm.style || ''}
                      onChange={(e) => setEditForm((f) => ({ ...f, style: e.target.value }))}
                      className="field"
                    />
                  </div>
                </div>
                <div>
                  <label htmlFor="edit-material" className="field-label">
                    Chất liệu
                  </label>
                  <input
                    id="edit-material"
                    type="text"
                    value={editForm.material || ''}
                    onChange={(e) => setEditForm((f) => ({ ...f, material: e.target.value }))}
                    className="field"
                  />
                </div>
              </section>

              <section className="space-y-4 border-t border-line pt-5">
                <h4 className="text-sm font-semibold text-ink">Cảm giác khi mặc</h4>
                <ScaleInput
                  label="Độ trang trọng"
                  value={editForm.formality_level || 3}
                  onChange={(level) => setEditForm((f) => ({ ...f, formality_level: level }))}
                  lowLabel="Thường ngày"
                  highLabel="Dạ tiệc"
                />
                <ScaleInput
                  label="Độ thoải mái"
                  value={editForm.comfort_level || 3}
                  onChange={(level) => setEditForm((f) => ({ ...f, comfort_level: level }))}
                  lowLabel="Gò bó"
                  highLabel="Rất thoải mái"
                  testIdPrefix="edit-comfort"
                />
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label htmlFor="edit-silhouette-level" className="field-label">
                      Phom dáng
                    </label>
                    <select
                      id="edit-silhouette-level"
                      data-testid="edit-silhouette-level"
                      value={editForm.silhouette_level ?? 3}
                      onChange={(e) => setEditForm((f) => ({ ...f, silhouette_level: parseInt(e.target.value, 10) }))}
                      className="field"
                    >
                      <option value={1}>Rất ôm sát</option>
                      <option value={2}>Ôm vừa</option>
                      <option value={3}>Tiêu chuẩn</option>
                      <option value={4}>Rộng</option>
                      <option value={5}>Oversized</option>
                    </select>
                  </div>
                  {hasGarmentLength(editingItem.category) && (
                  <div>
                    <label htmlFor="edit-length" className="field-label">
                      Độ dài
                    </label>
                    <select
                      id="edit-length"
                      data-testid="edit-length"
                      value={editForm.length || 'hip'}
                      onChange={(e) => setEditForm((f) => ({ ...f, length: e.target.value }))}
                      className="field"
                    >
                      <option value="cropped">Lửng</option>
                      <option value="waist">Ngang eo</option>
                      <option value="hip">Ngang hông</option>
                      <option value="long">Dáng dài</option>
                    </select>
                  </div>
                  )}
                </div>
              </section>

              <section className="space-y-3 border-t border-line pt-5">
                <h4 className="text-sm font-semibold text-ink">Công dụng</h4>
                <div className="flex flex-wrap gap-2">
                  {FUNCTIONAL_FLAG_VALUES.map((flag) => {
                    const currentFlags = editForm.functional_flags || [];
                    const isSelected = currentFlags.includes(flag);
                    return (
                      <button
                        key={flag}
                        type="button"
                        data-testid={`edit-flag-${flag}`}
                        aria-pressed={isSelected}
                        onClick={() => {
                          const nextFlags = isSelected
                            ? currentFlags.filter((f) => f !== flag)
                            : [...currentFlags, flag];
                          setEditForm((f) => ({ ...f, functional_flags: nextFlags }));
                        }}
                        className="chip"
                      >
                        {FUNCTION_TAG_NAMES[flag]}
                      </button>
                    );
                  })}
                </div>
              </section>

              {editError && (
                <p role="alert" className="notice notice-danger">
                  {editError}
                </p>
              )}
            </div>

            <div className="sticky bottom-0 flex justify-end gap-2 border-t border-line bg-surface px-6 py-4">
              <button type="button" onClick={closeEdit} disabled={savingEdit} className="btn btn-ghost">
                Hủy
              </button>
              <button
                type="button"
                data-testid="save-edit-btn"
                disabled={savingEdit}
                onClick={handleSaveEdit}
                className="btn btn-primary"
              >
                {savingEdit ? 'Đang lưu…' : 'Lưu thay đổi'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete confirmation */}
      {deletingItemId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4 backdrop-blur-[2px]"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeDelete();
          }}
        >
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-item-title"
            className="w-full max-w-sm rounded-3xl bg-surface p-6 shadow-2xl"
          >
            <h3 id="delete-item-title" className="display text-xl">
              Xóa {deletingItem ? `“${deletingItem.display_name_vi || deletingItem.sub_category}”` : 'món đồ này'}?
            </h3>
            <p className="mt-2 text-[0.9375rem] leading-relaxed text-ink-2">
              Món đồ sẽ không còn xuất hiện trong các gợi ý phối đồ sau này.
            </p>
            {deleteError && (
              <p role="alert" className="notice notice-danger mt-4">
                {deleteError}
              </p>
            )}
            <div className="mt-6 flex justify-end gap-2">
              <button type="button" onClick={closeDelete} disabled={deleting} className="btn btn-ghost">
                Hủy
              </button>
              <button
                type="button"
                data-testid="confirm-delete-btn"
                disabled={deleting}
                onClick={() => handleDelete(deletingItemId)}
                className="btn btn-danger"
              >
                {deleting ? 'Đang xóa…' : 'Xóa'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
