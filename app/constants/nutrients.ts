// backend/nutrition_constants.py의 SELECTABLE_NUTRIENT_KEYS / DEFAULT_SELECTED_NUTRIENTS /
// MAX_SELECTED_NUTRIENTS와 값을 맞춰서 유지한다 (두 언어 간 공유 코드젠이 없어 수동 동기화).
export type SelectableNutrientKey =
  | 'carbohydrate'
  | 'sugar'
  | 'energy'
  | 'fat'
  | 'iron'
  | 'protein'
  | 'sodium';

export const SELECTABLE_NUTRIENT_KEYS: SelectableNutrientKey[] = [
  'carbohydrate',
  'sugar',
  'energy',
  'fat',
  'iron',
  'protein',
  'sodium',
];

export const NUTRIENT_LABELS_KO: Record<SelectableNutrientKey, string> = {
  carbohydrate: '탄수화물',
  sugar: '당류',
  energy: '에너지',
  fat: '지방',
  iron: '철분',
  protein: '단백질',
  sodium: '나트륨',
};

export const DEFAULT_SELECTED_NUTRIENTS: SelectableNutrientKey[] = [
  'carbohydrate',
  'sugar',
  'sodium',
];

export const MAX_SELECTED_NUTRIENTS = 3;