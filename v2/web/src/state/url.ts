/** The sorted column and its direction are part of the board's URL (contract §11), so a view can be sent on.
 *
 * `?sort=mcap&dir=asc`. Nothing else of a board's view is in the URL yet: saved layouts are not decided
 * (contract §14), and the density switch is the board's own control.
 */
import type { SortDirection } from '../board/envelope';

export type Sort = { key: string; direction: SortDirection };

export function sortFromSearch(search: string): Sort | null {
  const params = new URLSearchParams(search);
  const key = params.get('sort');
  if (!key) return null;
  const dir = params.get('dir');
  return { key, direction: dir === 'asc' ? 'asc' : 'desc' };
}

export function searchWithSort(search: string, sort: Sort | null): string {
  const params = new URLSearchParams(search);
  if (sort === null) {
    params.delete('sort');
    params.delete('dir');
  } else {
    params.set('sort', sort.key);
    params.set('dir', sort.direction);
  }
  const text = params.toString();
  return text === '' ? '' : `?${text}`;
}
