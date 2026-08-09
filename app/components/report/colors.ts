// 리포트 화면에만 나오는 색. authColors에 이미 있는 값(#F47E8A, #FFF0F0, #ECDEDD,
// #848484, #4A4A4A)은 여기에 다시 적지 않는다 — 토큰이 없는 것만 모은다.
export const reportColors = {
  /** 배너 배경 그라데이션 (왼쪽 → 오른쪽). */
  bannerGradientFrom: '#FFECEE',
  bannerGradientTo: '#FFF8F8',
  /** 일간/주간 토글의 트랙 배경. 흰색보다 아주 살짝 분홍이 돈다. */
  toggleTrack: '#FFFDFD',
  /** 선택된 쪽 알약의 테두리. 배경(authColors.pinkLight)보다 진한 분홍. */
  toggleActiveBorder: '#F8BFC0',
  /** AI 분석 요약 카드 배경 — 다른 카드와 달리 흰색이 아니다. */
  aiCardBg: '#FFF5F3',
  /** 지난주 대비 증가(▲). Figma text/up. */
  comparisonUp: '#DF3535',
  /** 지난주 대비 감소(▼). Figma text/down. */
  comparisonDown: '#5D98EB',
};
