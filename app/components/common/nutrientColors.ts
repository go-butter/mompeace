import { authColors } from '@/components/auth/colors';
import { NutrientIconKey } from '@/components/common/nutrientIcons';
import { homeColors } from '@/components/home/colors';

/** 영양소 하나의 색. value는 큰 숫자·게이지 채움·아이콘·권장 기준 대비 퍼센트에,
 *  track은 게이지 바탕에 쓴다. */
export interface NutrientColor {
  value: string;
  track: string;
}

// ── homeColors 키 이름 주의 ────────────────────────────────────────────────
// homeColors.sugar는 초록(#5B9926), homeColors.sodium은 주황(#E37808)이다. 이 이름들은
// 영양소가 아니라 홈 화면 상태 칩(여유/안전)에서 쓰던 색을 가리키던 것이라, 실제 영양소와
// 반대로 붙어 있다. 리포트 디자인에서 나트륨은 초록, 당류는 머스터드이므로 여기서 한 번만
// 바꿔 담아두고, 아래 맵에서는 올바른 이름으로만 쓴다. 토큰 자체는 이름을 바꾸지 않는다 —
// summaryColors.ts와 OCR 확인 화면이 지금 이름 그대로 의존하고 있다.
const GREEN = homeColors.sugar; // #5B9926 / #F4F8EF
const MUSTARD = homeColors.sodium; // #E37808 / #FDF7EC

// 값이 없는 영양소의 대비책. 분홍은 카페인의 색이라 여기에 쓰면 안 된다 — 색이 없는
// 영양소가 전부 카페인처럼 보이게 된다.
export const DEFAULT_NUTRIENT_COLOR: NutrientColor = {
  value: homeColors.water.value,
  track: homeColors.water.bg,
};

/**
 * 영양소별 고유색. 상태(여유/안전/위험)가 아니라 영양소 정체성으로 색을 정한다 —
 * 같은 영양소는 수치가 어떻든 항상 같은 색이고, 일간↔주간을 오가도 색이 바뀌지 않는다.
 * 상태는 색이 아니라 숫자와 퍼센트로 읽는다.
 *
 * 카페인·당류·나트륨은 Figma 프레임(46:461 / 46:444 / 46:426)에서 그대로 가져왔고,
 * 나머지 다섯은 프레임에 색이 없어 새로 정한 값이다. 지난주 대비의 빨강(#DF3535)·
 * 파랑(#5D98EB)과 겹치지 않도록 골랐다.
 *
 * Record라서 SELECTABLE_NUTRIENT_KEYS에 영양소가 추가되면 색을 정하기 전까지
 * 컴파일이 되지 않는다 — 색 없는 영양소가 조용히 기본색으로 새는 것을 막는다.
 */
export const NUTRIENT_COLORS: Record<NutrientIconKey, NutrientColor> = {
  caffeine: { value: authColors.pink, track: authColors.pinkLight },
  sodium: { value: GREEN.value, track: GREEN.bg },
  // Figma는 #E3A22B지만 토큰(#E37808)을 유지한다 — 같은 머스터드 계열에서 토큰 쪽이
  // 살짝 진한 정도의 차이다.
  sugar: { value: MUSTARD.value, track: MUSTARD.bg },
  carbohydrate: { value: '#4A90A4', track: '#EDF4F6' },
  protein: { value: '#7B68B5', track: '#F1EFF8' },
  fat: { value: '#C08552', track: '#F9F2EA' },
  iron: { value: '#9E4B5C', track: '#F6EDEF' },
  // 에너지는 특정 성분이 아니라 총량 지표라 중립적인 슬레이트를 쓴다.
  energy: DEFAULT_NUTRIENT_COLOR,
};

/** 서버가 주는 key는 string이라 맵에 없는 값이 올 수 있다. 그때도 분홍으로 떨어지지 않는다. */
export function nutrientColorFor(key: string): NutrientColor {
  return NUTRIENT_COLORS[key as NutrientIconKey] ?? DEFAULT_NUTRIENT_COLOR;
}
