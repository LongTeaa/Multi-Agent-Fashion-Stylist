'use client';

import { useCallback, useEffect, useState } from 'react';
import { getGarmentTaxonomy } from './api';
import type { GarmentTaxonomy } from '@/types/wardrobe';

export function useGarmentTaxonomy() {
  const [taxonomy, setTaxonomy] = useState<GarmentTaxonomy>({ groups: [] });
  const [taxonomyError, setTaxonomyError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const retryTaxonomy = useCallback(() => setAttempt((value) => value + 1), []);
  useEffect(() => {
    let active = true;
    void getGarmentTaxonomy().then((result) => {
      if (active) { setTaxonomy(result); setTaxonomyError(false); }
    }).catch(() => { if (active) setTaxonomyError(true); });
    return () => { active = false; };
  }, [attempt]);
  return { taxonomy, taxonomyError, retryTaxonomy };
}
