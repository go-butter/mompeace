import { authColors } from '@/components/auth/colors';
import { homeColors } from '@/components/home/colors';

// /intake/summary는 status_label 문자열(여유/안전/위험/충분/부족/정보없음)로만 결과를
// 주므로, 기존 homeColors(영양소 키 기준)와 달리 라벨 문자열을 키로 삼는 맵이 필요하다.
// 여유/충분은 같은 "양호" 의미, 안전/부족은 같은 "중간 경고" 의미라 색을 공유한다.
export const summaryStatusColors: Record<string, { label: string; value: string; bg: string }> = {
  여유: homeColors.sugar,
  충분: homeColors.sugar,
  안전: homeColors.sodium,
  부족: homeColors.sodium,
  위험: { label: authColors.pink, value: authColors.pink, bg: authColors.pinkLight },
  정보없음: homeColors.water,
};

export const DEFAULT_SUMMARY_STATUS_COLORS = homeColors.water;
