export type VisualStatus = 'safe' | 'caution' | 'avoid';

export const scanStatusColors: Record<VisualStatus, string> = {
  safe: '#5b9926',
  caution: '#e3a22b',
  avoid: '#c94603',
};

export const scanBannerColors: Record<VisualStatus, { bg: string; border: string; title: string }> = {
  safe: { bg: '#fbfff9', border: '#90c95e', title: '#5b9926' },
  caution: { bg: '#fdf7ec', border: '#e37808', title: '#e37808' },
  avoid: { bg: '#fff0f0', border: '#f47e8a', title: '#df3535' },
};

export const scanBannerLabel: Record<VisualStatus, string> = {
  safe: '안전',
  caution: '주의',
  avoid: '위험',
};

export function toVisualStatus(
  status: 'safe' | 'caution' | 'avoid' | 'unknown' | 'check_required'
): VisualStatus {
  if (status === 'safe' || status === 'caution' || status === 'avoid') return status;
  return 'caution';
}

export function allergyToVisualStatus(status: 'check_required' | 'safe'): VisualStatus {
  return status === 'safe' ? 'safe' : 'avoid';
}
