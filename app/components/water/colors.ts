import { authColors } from '@/components/auth/colors';

// 버튼/미니 서클: 앱 메인 브랜드 컬러(authColors.pink) 기반 톤.
const PINK_TINT = '#FABFC5'; // authColors.pink를 흰색과 50% 블렌드 - 베이비 핑크
const PALE_PINK_TINT = '#FCDFE2'; // authColors.pink를 흰색과 75% 블렌드 - 버튼 배경 전용, 더 옅은 톤

// 웨이브 채우기(큰 원): 물을 연상시키는 하늘색 유지 - 브랜드 핑크와는 별개 팔레트.
const WAVE_FRONT = '#C2E1F5';
const WAVE_BACK = '#DCF0FA';

export const waterColors = {
  waveFront: WAVE_FRONT,
  waveBack: WAVE_BACK,
  track: '#F5F5F8',
  primaryButtonBg: PALE_PINK_TINT,
  miniCircleFill: PINK_TINT,
  chip: { label: authColors.pink, value: authColors.pink, bg: '#FFF0F0' },
};
