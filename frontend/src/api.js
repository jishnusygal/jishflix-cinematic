export async function api(path, options = {}) {
  const response = await fetch('/api' + path, {
    credentials: 'same-origin', ...options,
    headers: { 'X-Requested-With': 'Jishflix', ...(options.body ? {'Content-Type': 'application/json'} : {}), ...options.headers },
  });
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('session-expired'));
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : `Request failed (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}
export const post = (path, body = {}) => api(path, {method: 'POST', body: JSON.stringify(body)});
export const jf = (path, options) => api('/jellyfin/' + path, options);
export function artwork(item, backdrop = false) {
  if (!item) return null;
  let id = item.Id, type = 'Primary', tag = item.ImageTags?.Primary;
  if (backdrop && item.BackdropImageTags?.length) { type = 'Backdrop'; tag = item.BackdropImageTags[0]; }
  else if (backdrop && item.ParentBackdropItemId) { id = item.ParentBackdropItemId; type = 'Backdrop'; tag = item.ParentBackdropImageTags?.[0]; }
  else if (!tag && type === 'Primary' && item.AlbumId && item.AlbumPrimaryImageTag) { id = item.AlbumId; tag = item.AlbumPrimaryImageTag; }
  if (!tag && type === 'Primary') return null;
  return `/api/jellyfin/Items/${encodeURIComponent(id)}/Images/${type}?maxWidth=${backdrop ? 1920 : 480}&quality=85&tag=${encodeURIComponent(tag || '')}`;
}
export const minutes = ticks => Math.round((ticks || 0) / 600000000);
export const timeLabel = ticks => { const m = minutes(ticks); return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m`; };
