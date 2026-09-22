'use client';

import React, { useState } from 'react';
import { IngestionWorkflow } from '@/components/ingestion/IngestionWorkflow';
import { WardrobeInventory } from '@/components/wardrobe/WardrobeInventory';

export function WardrobeView() {
  const [viewMode, setViewMode] = useState<'inventory' | 'ingestion'>('inventory');

  return (
    <div className="space-y-6">
      {viewMode === 'inventory' ? (
        <WardrobeInventory onSwitchToIngestion={() => setViewMode('ingestion')} />
      ) : (
        <div className="space-y-6">
          <div className="flex items-center justify-between pb-4 border-b border-[#E8E5DE]">
            <button
              type="button"
              data-testid="btn-back-to-inventory"
              onClick={() => setViewMode('inventory')}
              className="tactile-btn inline-flex items-center gap-2 px-4 py-2 rounded-full border border-[#E8E5DE] bg-white text-xs font-mono uppercase tracking-wider text-[#1A1918] hover:bg-[#F5F4F0] hover:border-[#D5D1C7] transition-all shadow-2xs"
            >
              <span aria-hidden="true">←</span>
              <span>Quay lại tủ đồ</span>
            </button>
            <span className="text-xs font-mono uppercase tracking-wider text-[#736E65]">
              Số Hóa & Nhận Diện AI
            </span>
          </div>
          <IngestionWorkflow onFinish={() => setViewMode('inventory')} />
        </div>
      )}
    </div>
  );
}

