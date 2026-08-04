export function formatNumber(value: number): string {
  return `${Math.round(value)}`;
}

export function formatNutrient(value: number | null | undefined, unit: string): string {
  if (value == null || typeof value !== 'number' || !Number.isFinite(value)) {
    return '정보 없음';
  }
  return `${formatNumber(value)}${unit}`;
}
