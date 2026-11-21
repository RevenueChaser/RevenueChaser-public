import { describe, expect, it } from 'vitest';

import { searchWithSort, sortFromSearch } from './url';

/** Contract §11: the sorted column and its direction are part of the board's URL, so a sorted view can be sent
 * to someone and comes back the same. */
describe('the sort in the URL', () => {
  it('reads a sort and defaults an unknown direction to descending', () => {
    expect(sortFromSearch('?sort=mcap&dir=asc')).toEqual({ key: 'mcap', direction: 'asc' });
    expect(sortFromSearch('?sort=mcap')).toEqual({ key: 'mcap', direction: 'desc' });
    expect(sortFromSearch('?sort=mcap&dir=sideways')).toEqual({ key: 'mcap', direction: 'desc' });
    expect(sortFromSearch('')).toBeNull();
  });

  it('writes one back and comes back the same', () => {
    const search = searchWithSort('?view=states', { key: 'volume', direction: 'asc' });
    expect(sortFromSearch(search)).toEqual({ key: 'volume', direction: 'asc' });
    expect(search).toContain('view=states');
  });

  it('removes it rather than leaving an empty key behind', () => {
    expect(searchWithSort('?sort=mcap&dir=desc', null)).toBe('');
    expect(searchWithSort('?sort=mcap&dir=desc&view=states', null)).toBe('?view=states');
  });

  it('carries a stacked price figure as its own sort key', () => {
    expect(sortFromSearch('?sort=quote.d1&dir=desc')).toEqual({ key: 'quote.d1', direction: 'desc' });
  });
});
