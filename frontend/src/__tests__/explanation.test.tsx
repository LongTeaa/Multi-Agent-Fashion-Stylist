import { describe, expect, it } from 'vitest';
import { splitExplanation } from '@/lib/explanation';

describe('splitExplanation', () => {
  it('returns garment names without brackets and keeps the surrounding text', () => {
    expect(splitExplanation('Phối [Áo sơ mi trắng], [Quần tây xám]. Hợp dịp.')).toEqual([
      { text: 'Phối ', isItem: false },
      { text: 'Áo sơ mi trắng', isItem: true },
      { text: ', ', isItem: false },
      { text: 'Quần tây xám', isItem: true },
      { text: '. Hợp dịp.', isItem: false },
    ]);
  });

  it('leaves text without brackets unchanged', () => {
    expect(splitExplanation('Bộ đồ thoáng mát.')).toEqual([{ text: 'Bộ đồ thoáng mát.', isItem: false }]);
  });

});
