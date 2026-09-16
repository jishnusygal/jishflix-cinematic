import { useEffect, useRef } from 'react';

export function chooseNext(current, candidates, direction) {
  const r = current.getBoundingClientRect();
  const x = r.left + r.width / 2, y = r.top + r.height / 2;
  const horizontal = direction === 'ArrowLeft' || direction === 'ArrowRight';
  const sign = direction === 'ArrowLeft' || direction === 'ArrowUp' ? -1 : 1;
  let best = null, score = Infinity;
  for (const element of candidates) {
    if (element === current) continue;
    const b = element.getBoundingClientRect();
    if (!b.width || !b.height || element.closest('[inert], [hidden]')) continue;
    const dx = b.left + b.width / 2 - x, dy = b.top + b.height / 2 - y;
    const primary = (horizontal ? dx : dy) * sign;
    if (primary <= 2) continue;
    const cross = Math.abs(horizontal ? dy : dx);
    const overlap = horizontal ? b.top < r.bottom && b.bottom > r.top : b.left < r.right && b.right > r.left;
    const candidateScore = primary + cross * 3 + (overlap ? 0 : 10000);
    if (candidateScore < score) { score = candidateScore; best = element; }
  }
  return best;
}

export default function useTVNavigation(onBack) {
  const back = useRef(onBack);
  useEffect(() => { back.current = onBack; }, [onBack]);
  useEffect(() => {
    function keydown(event) {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      const active = document.activeElement;
      const editable = active?.matches('input, textarea, select, [contenteditable="true"]');
      if (['Escape', 'GoBack', 'BrowserBack'].includes(event.key) || (event.key === 'Backspace' && !editable)) {
        event.preventDefault(); back.current?.(); return;
      }
      if (editable || active?.tagName === 'VIDEO') return;
      const scopes = document.querySelectorAll('[data-focus-scope]');
      const scope = scopes[scopes.length - 1] || document;
      const candidates = [...scope.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), [tabindex="0"]')]
        .filter(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden' && !el.closest('[inert], [hidden]'));
      if (event.key === 'Tab' && scopes.length && candidates.length) {
        if (event.shiftKey && active === candidates[0]) { event.preventDefault(); candidates.at(-1).focus(); }
        else if (!event.shiftKey && active === candidates.at(-1)) { event.preventDefault(); candidates[0].focus(); }
        return;
      }
      if (!event.key.startsWith('Arrow')) return;
      event.preventDefault();
      const next = !candidates.includes(active) ? candidates[0] : chooseNext(active, candidates, event.key);
      if (next) {
        next.focus({preventScroll: true});
        next.scrollIntoView({block: 'nearest', inline: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
      }
    }
    window.addEventListener('keydown', keydown);
    return () => window.removeEventListener('keydown', keydown);
  }, []);
}

export function useFocusScope(ref) {
  useEffect(() => {
    const previous = document.activeElement;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const frame = requestAnimationFrame(() => ref.current?.querySelector('button, input, a[href]')?.focus());
    return () => { cancelAnimationFrame(frame); document.body.style.overflow = oldOverflow; if (previous?.isConnected) previous.focus(); };
  }, [ref]);
}
