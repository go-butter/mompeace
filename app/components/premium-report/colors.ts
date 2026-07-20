import type { NutrientStatus } from '@/lib/api-client';

// Dedicated to the premium-report screen's 3 metric cards + chart.
// Not homeColors — that map's sugar/sodium assignment is inverted relative
// to the Figma mockup and belongs to the unrelated StatusChip pills.
export const nutrientColors = {
  caffeine: '#F47E8A',
  sugar: '#E3A22B',
  sodium: '#5B9926',
};

// "unknown" must render as a distinct gray, never collapsed into "caution"
// like scanStatusColors.toVisualStatus() does — this screen enforces NULL≠0.
export const statusColors: Record<NutrientStatus, string> = {
  safe: '#5B9926',
  caution: '#E3A22B',
  avoid: '#C94603',
  unknown: '#848484',
};

export const statusLabel: Record<NutrientStatus, string> = {
  safe: '안전',
  caution: '주의',
  avoid: '위험',
  unknown: '정보 없음',
};

export const referenceLineColor = '#DF3535';
