'use client';

import React, { useState } from 'react';
import { IngestionWorkflow } from '@/components/ingestion/IngestionWorkflow';
import { WardrobeInventory } from '@/components/wardrobe/WardrobeInventory';

export function WardrobeView() {
  const [activeTab, setActiveTab] = useState<'inventory' | 'ingestion'>('inventory');

  return (
    <div className="space-y-8">
      {/* Top Tab Switcher */}
      <div className="flex items-center justify-between border-b border-[#E8E5DE] pb-4">
        <div className="flex gap-2">
          <button
            data-testid="tab-inventory"
            onClick={() => setActiveTab('inventory')}
            className={`px-5 py-2.5 rounded-full text-xs font-mono uppercase tracking-wider transition-all ${
              activeTab === 'inventory'
                ? 'bg-[#1A1918] text-[#FBFBF9] font-medium shadow-xs'
                : 'bg-white border border-[#E8E5DE] text-[#5C564E] hover:border-[#D5D1C7] hover:text-[#1A1918]'
            }`}
          >
            👔 Tủ Đồ Của Tôi
          </button>
          <button
            data-testid="tab-ingestion"
            onClick={() => setActiveTab('ingestion')}
            className={`px-5 py-2.5 rounded-full text-xs font-mono uppercase tracking-wider transition-all ${
              activeTab === 'ingestion'
                ? 'bg-[#9C5234] text-white font-medium shadow-xs'
                : 'bg-white border border-[#E8E5DE] text-[#5C564E] hover:border-[#D5D1C7] hover:text-[#9C5234]'
            }`}
          >
            + Số Hóa Trang Phục Mới
          </button>
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'inventory' ? (
        <WardrobeInventory onSwitchToIngestion={() => setActiveTab('ingestion')} />
      ) : (
        <div className="space-y-4">
          <button
            onClick={() => setActiveTab('inventory')}
            className="text-xs font-mono text-[#736E65] hover:text-[#1A1918] flex items-center gap-1 mb-2"
          >
            ← Quay lại tủ đồ
          </button>
          <IngestionWorkflow />
        </div>
      )}
    </div>
  );
}
