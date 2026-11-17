'use client';

import React, { useState, useSyncExternalStore } from 'react';
import { IngestionWorkflow } from '@/components/ingestion/IngestionWorkflow';
import { WardrobeInventory } from '@/components/wardrobe/WardrobeInventory';
import { ArrowLeftIcon } from '@/components/ui/icons';
import { ACTIVE_INGESTION_BATCH_KEY, removeUrlParam } from '@/lib/browserState';

const ADD_PARAM = 'add';

const noopSubscribe = () => () => {};
const readWantsAdd = () => new URLSearchParams(window.location.search).has(ADD_PARAM);
const readHasPendingBatch = () => {
  try {
    return Boolean(window.sessionStorage.getItem(ACTIVE_INGESTION_BATCH_KEY));
  } catch {
    return false;
  }
};
const serverFalse = () => false;

export function WardrobeView() {
  // `?add=1` (from the home page or an error banner) opens the add flow directly.
  const wantsAdd = useSyncExternalStore(noopSubscribe, readWantsAdd, serverFalse);
  const hasPendingBatch = useSyncExternalStore(noopSubscribe, readHasPendingBatch, serverFalse);
  const [chosenMode, setChosenMode] = useState<'inventory' | 'ingestion' | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const viewMode = chosenMode ?? (wantsAdd ? 'ingestion' : 'inventory');

  const openIngestion = () => {
    setNotice(null);
    setChosenMode('ingestion');
  };

  const backToInventory = () => {
    removeUrlParam(ADD_PARAM);
    setChosenMode('inventory');
  };

  if (viewMode === 'ingestion') {
    return (
      <div>
        <div className="mb-6 flex items-center justify-between gap-3">
          <button
            type="button"
            data-testid="btn-back-to-inventory"
            onClick={backToInventory}
            className="btn btn-ghost btn-sm -ml-2"
          >
            <ArrowLeftIcon size={16} />
            <span>Quay lại tủ đồ</span>
          </button>
        </div>
        <IngestionWorkflow
          onFinish={(createdItemIds) => {
            const count = createdItemIds?.length ?? 0;
            setNotice(count > 0 ? `Đã thêm ${count} món vào tủ đồ.` : null);
            backToInventory();
          }}
        />
      </div>
    );
  }

  return (
    <WardrobeInventory
      onSwitchToIngestion={openIngestion}
      notice={notice}
      onDismissNotice={() => setNotice(null)}
      hasPendingBatch={hasPendingBatch}
    />
  );
}
