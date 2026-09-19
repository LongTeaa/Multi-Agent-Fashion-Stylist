'use client';

import React, { useCallback, useEffect, useState } from 'react';
import type { WardrobeCategory, WardrobeItem, WardrobeItemUpdatePayload } from '@/types/wardrobe';
import { deleteWardrobeItem, listWardrobeItems, updateWardrobeItem } from '@/lib/api';

const CATEGORIES: { label: string; value: WardrobeCategory | 'all' }[] = [
  { label: 'Tất cả', value: 'all' },
  { label: 'Áo', value: 'top' },
  { label: 'Quần / Váy', value: 'bottom' },
  { label: 'Đầm', value: 'dress' },
  { label: 'Giày dép', value: 'footwear' },
  { label: 'Áo khoác', value: 'outerwear' },
  { label: 'Phụ kiện', value: 'accessory' },
];

const CATEGORY_NAMES: Record<WardrobeCategory, string> = {
  top: 'Áo',
  bottom: 'Quần / Váy',
  dress: 'Đầm',
  footwear: 'Giày dép',
  outerwear: 'Áo khoác',
  accessory: 'Phụ kiện',
};

interface WardrobeInventoryProps {
  onSwitchToIngestion?: () => void;
}

export function WardrobeInventory({ onSwitchToIngestion }: WardrobeInventoryProps) {
  const [items, setItems] = useState<WardrobeItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedCategory, setSelectedCategory] = useState<WardrobeCategory | 'all'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 12;

  // Edit modal state
  const [editingItem, setEditingItem] = useState<WardrobeItem | null>(null);
  const [editForm, setEditForm] = useState<WardrobeItemUpdatePayload>({});
  const [savingEdit, setSavingEdit] = useState(false);

  // Delete modal state
  const [deletingItemId, setDeletingItemId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listWardrobeItems({
        category: selectedCategory === 'all' ? undefined : selectedCategory,
        text: searchQuery.trim() || undefined,
        page,
        page_size: pageSize,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể tải danh sách trang phục.');
    } finally {
      setLoading(false);
    }
  }, [selectedCategory, searchQuery, page]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchItems();
  };

  const handleOpenEdit = (item: WardrobeItem) => {
    setEditingItem(item);
    setEditForm({
      sub_category: item.sub_category,
      primary_color: item.primary_color,
      style: item.style,
      material: item.material,
      fit: item.fit,
      formality_level: item.formality_level,
      is_active: item.is_active,
    });
  };

  const handleSaveEdit = async () => {
    if (!editingItem) return;
    setSavingEdit(true);
    try {
      const updated = await updateWardrobeItem(editingItem.id, editForm);
      setItems((prev) => prev.map((it) => (it.id === updated.id ? updated : it)));
      setEditingItem(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Cập nhật trang phục thất bại.');
    } finally {
      setSavingEdit(false);
    }
  };

  const handleDelete = async (itemId: string) => {
    setDeleting(true);
    try {
      await deleteWardrobeItem(itemId);
      setItems((prev) => prev.filter((it) => it.id !== itemId));
      setTotal((prev) => Math.max(0, prev - 1));
      setDeletingItemId(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Xóa trang phục thất bại.');
    } finally {
      setDeleting(false);
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="space-y-6">
      {/* Header & Filter Controls */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h2 className="font-serif text-2xl sm:text-3xl text-[#1A1918]">Tủ Đồ Của Bạn</h2>
          <p className="text-sm text-[#736E65] mt-1">
            Quản lý {total} món trang phục đã được số hóa và sẵn sàng phối đồ.
          </p>
        </div>

        <form onSubmit={handleSearchSubmit} className="flex gap-2">
          <input
            type="text"
            data-testid="wardrobe-search-input"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Tìm theo loại, màu, phong cách..."
            className="px-4 py-2 text-sm rounded-xl border border-[#E8E5DE] bg-white text-[#1A1918] placeholder-[#A8A29E] focus:outline-hidden focus:ring-2 focus:ring-[#9C5234]/30 focus:border-[#9C5234]"
          />
          <button
            type="submit"
            className="px-4 py-2 rounded-xl bg-[#1A1918] text-[#FBFBF9] text-xs font-mono uppercase tracking-wider hover:bg-[#2D2420] transition-colors"
          >
            Tìm
          </button>
        </form>
      </div>

      {/* Category Filter Pills */}
      <div className="flex flex-wrap gap-2 pt-2 border-t border-[#E8E5DE]">
        {CATEGORIES.map((cat) => {
          const isActive = selectedCategory === cat.value;
          return (
            <button
              key={cat.value}
              data-testid={`category-filter-${cat.value}`}
              onClick={() => {
                setSelectedCategory(cat.value);
                setPage(1);
              }}
              className={`px-3.5 py-1.5 rounded-full text-xs font-mono uppercase tracking-wider transition-all ${
                isActive
                  ? 'bg-[#1A1918] text-[#FBFBF9] font-medium shadow-xs'
                  : 'bg-white border border-[#E8E5DE] text-[#5C564E] hover:border-[#D5D1C7] hover:text-[#1A1918]'
              }`}
            >
              {cat.label}
            </button>
          );
        })}
      </div>

      {/* Loading & Error States */}
      {loading && (
        <div className="py-20 text-center text-[#736E65] font-mono text-sm" data-testid="wardrobe-loading">
          Đang tải danh sách trang phục...
        </div>
      )}

      {error && !loading && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && items.length === 0 && (
        <div className="py-16 text-center bg-white rounded-2xl border border-dashed border-[#E8E5DE] p-8">
          <div className="w-16 h-16 rounded-full bg-[#F5F4F0] flex items-center justify-center mx-auto mb-4 text-2xl">
            👔
          </div>
          <h3 className="font-serif text-lg text-[#1A1918] mb-1">Chưa có trang phục nào</h3>
          <p className="text-sm text-[#736E65] max-w-md mx-auto mb-6">
            {searchQuery || selectedCategory !== 'all'
              ? 'Không tìm thấy trang phục phù hợp với bộ lọc hiện tại.'
              : 'Hãy bắt đầu bằng cách tải lên ảnh trang phục để AI tự động nhận diện và số hóa.'}
          </p>
          {onSwitchToIngestion && (
            <button
              onClick={onSwitchToIngestion}
              className="px-5 py-2.5 rounded-full bg-[#9C5234] text-white text-xs font-mono uppercase tracking-wider hover:bg-[#854429] transition-colors shadow-xs"
            >
              + Số Hóa Trang Phục Ngay
            </button>
          )}
        </div>
      )}

      {/* Items Grid */}
      {!loading && !error && items.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
          {items.map((item) => (
            <div
              key={item.id}
              data-testid={`wardrobe-item-card-${item.id}`}
              className="group relative flex flex-col bg-white rounded-2xl border border-[#E8E5DE] overflow-hidden hover:shadow-md transition-all"
            >
              {/* Image Preview */}
              <div className="aspect-4/3 w-full bg-[#F5F4F0] relative overflow-hidden flex items-center justify-center">
                {item.thumbnail_url || item.media_url ? (
                  <img
                    src={item.thumbnail_url || item.media_url || ''}
                    alt={item.sub_category}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                  />
                ) : (
                  <span className="text-3xl opacity-40">✨</span>
                )}
                <span className="absolute top-2.5 left-2.5 px-2 py-0.5 rounded-md text-[10px] font-mono uppercase tracking-wider bg-black/60 backdrop-blur-xs text-white">
                  {CATEGORY_NAMES[item.category] || item.category}
                </span>
                {item.times_worn > 0 && (
                  <span className="absolute top-2.5 right-2.5 px-2 py-0.5 rounded-md text-[10px] font-mono bg-[#9C5234] text-white">
                    Mặc {item.times_worn} lần
                  </span>
                )}
              </div>

              {/* Item Info */}
              <div className="p-4 flex-1 flex flex-col justify-between">
                <div>
                  <h4 className="font-serif text-base text-[#1A1918] capitalize mb-1">
                    {item.sub_category}
                  </h4>
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    <span className="text-[11px] px-2 py-0.5 rounded-md bg-[#F5F4F0] text-[#5C564E] font-mono">
                      {item.primary_color}
                    </span>
                    <span className="text-[11px] px-2 py-0.5 rounded-md bg-[#F5F4F0] text-[#5C564E] font-mono">
                      {item.style}
                    </span>
                    <span className="text-[11px] px-2 py-0.5 rounded-md bg-[#F5F4F0] text-[#5C564E] font-mono">
                      Trang trọng {item.formality_level}/5
                    </span>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center justify-between pt-3 border-t border-[#F5F4F0] text-xs font-mono">
                  <button
                    data-testid={`edit-item-${item.id}`}
                    onClick={() => handleOpenEdit(item)}
                    className="text-[#9C5234] hover:text-[#854429] font-medium"
                  >
                    Chỉnh sửa
                  </button>
                  <button
                    data-testid={`delete-item-${item.id}`}
                    onClick={() => setDeletingItemId(item.id)}
                    className="text-red-600 hover:text-red-700 font-medium"
                  >
                    Xóa
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center items-center gap-2 pt-6">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="px-3 py-1.5 rounded-lg border border-[#E8E5DE] text-xs font-mono disabled:opacity-30"
          >
            ← Trước
          </button>
          <span className="text-xs font-mono text-[#736E65]">
            Trang {page} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            className="px-3 py-1.5 rounded-lg border border-[#E8E5DE] text-xs font-mono disabled:opacity-30"
          >
            Sau →
          </button>
        </div>
      )}

      {/* Edit Modal */}
      {editingItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border border-[#E8E5DE] space-y-4">
            <h3 className="font-serif text-xl text-[#1A1918]">Chỉnh Sửa Trang Phục</h3>
            <div className="space-y-3 text-sm">
              <div>
                <label className="block text-xs font-mono text-[#736E65] mb-1">Tên / Phân loại</label>
                <input
                  type="text"
                  data-testid="edit-sub-category"
                  value={editForm.sub_category || ''}
                  onChange={(e) => setEditForm((f) => ({ ...f, sub_category: e.target.value }))}
                  className="w-full px-3 py-1.5 rounded-lg border border-[#E8E5DE]"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-mono text-[#736E65] mb-1">Màu chính</label>
                  <input
                    type="text"
                    data-testid="edit-primary-color"
                    value={editForm.primary_color || ''}
                    onChange={(e) => setEditForm((f) => ({ ...f, primary_color: e.target.value }))}
                    className="w-full px-3 py-1.5 rounded-lg border border-[#E8E5DE]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-mono text-[#736E65] mb-1">Phong cách</label>
                  <input
                    type="text"
                    data-testid="edit-style"
                    value={editForm.style || ''}
                    onChange={(e) => setEditForm((f) => ({ ...f, style: e.target.value }))}
                    className="w-full px-3 py-1.5 rounded-lg border border-[#E8E5DE]"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-mono text-[#736E65] mb-1">Chất liệu</label>
                  <input
                    type="text"
                    value={editForm.material || ''}
                    onChange={(e) => setEditForm((f) => ({ ...f, material: e.target.value }))}
                    className="w-full px-3 py-1.5 rounded-lg border border-[#E8E5DE]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-mono text-[#736E65] mb-1">Độ trang trọng (1-5)</label>
                  <input
                    type="number"
                    min={1}
                    max={5}
                    value={editForm.formality_level || 3}
                    onChange={(e) =>
                      setEditForm((f) => ({ ...f, formality_level: parseInt(e.target.value, 10) }))
                    }
                    className="w-full px-3 py-1.5 rounded-lg border border-[#E8E5DE]"
                  />
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-[#E8E5DE]">
              <button
                onClick={() => setEditingItem(null)}
                className="px-4 py-2 rounded-xl text-xs font-mono uppercase text-[#736E65] hover:bg-[#F5F4F0]"
              >
                Hủy
              </button>
              <button
                data-testid="save-edit-btn"
                disabled={savingEdit}
                onClick={handleSaveEdit}
                className="px-4 py-2 rounded-xl bg-[#1A1918] text-[#FBFBF9] text-xs font-mono uppercase tracking-wider hover:bg-[#2D2420] disabled:opacity-50"
              >
                {savingEdit ? 'Đang lưu...' : 'Lưu Thay Đổi'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deletingItemId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl max-w-sm w-full p-6 shadow-xl border border-[#E8E5DE] space-y-4">
            <h3 className="font-serif text-lg text-[#1A1918]">Xác Nhận Xóa</h3>
            <p className="text-sm text-[#736E65]">
              Bạn có chắc chắn muốn xóa trang phục này khỏi tủ đồ? Thao tác này sẽ ẩn món đồ khỏi các gợi ý phối đồ tương lai.
            </p>
            <div className="flex justify-end gap-2 pt-2 border-t border-[#E8E5DE]">
              <button
                onClick={() => setDeletingItemId(null)}
                className="px-4 py-2 rounded-xl text-xs font-mono uppercase text-[#736E65] hover:bg-[#F5F4F0]"
              >
                Hủy
              </button>
              <button
                data-testid="confirm-delete-btn"
                disabled={deleting}
                onClick={() => handleDelete(deletingItemId)}
                className="px-4 py-2 rounded-xl bg-red-600 text-white text-xs font-mono uppercase tracking-wider hover:bg-red-700 disabled:opacity-50"
              >
                {deleting ? 'Đang xóa...' : 'Xác Nhận Xóa'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
