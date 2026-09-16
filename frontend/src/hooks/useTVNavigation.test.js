import { describe, it, expect } from 'vitest';
import { chooseNext } from './useTVNavigation';
const box = (left, top, width = 100, height = 100) => ({getBoundingClientRect: () => ({left, top, width, height, right:left+width, bottom:top+height}), closest: () => null});
describe('TV spatial navigation', () => {
  it('prefers the same row over a closer diagonal card', () => {
    const current = box(0,0), next = box(140,0), diagonal = box(30,120);
    expect(chooseNext(current, [diagonal,next], 'ArrowRight')).toBe(next);
  });
  it('moves between rows and respects direction at a boundary', () => {
    const current = box(200,200), above = box(200,40), left = box(40,200);
    expect(chooseNext(current,[above,left], 'ArrowUp')).toBe(above);
    expect(chooseNext(current,[above,left], 'ArrowRight')).toBe(null);
  });
  it('ignores hidden and inert elements', () => {
    const current = box(0,0), hidden = box(110,0,0,0), inert = {...box(110,0), closest:() => ({})}, visible = box(220,0);
    expect(chooseNext(current,[hidden,inert,visible], 'ArrowRight')).toBe(visible);
  });
});
