import { useState } from 'react';
import { LayoutChangeEvent, StyleSheet, Text, View } from 'react-native';
import Svg, { G, Rect } from 'react-native-svg';

import { authColors } from '@/components/auth/colors';
import { nutrientColorFor } from '@/components/common/nutrientColors';
import { fonts } from '@/constants/fonts';
import { ReportChart, ReportChartItem, ReportChartNutrient } from '@/lib/api-client';

const PLOT_HEIGHT = 140;
// 막대/선이 위쪽 끝에 딱 붙지 않도록 남겨두는 여백 — 값이 축 최댓값에 가까워도
// 잘리는 느낌 없이 보이게 한다.
const TOP_PADDING = 12;
const USABLE_HEIGHT = PLOT_HEIGHT - TOP_PADDING;

const BAR_GROUP_WIDTH_RATIO = 0.6;
const BAR_GAP = 4;
// 막대 모서리 반경. 값이 작아 barHeight가 이보다 작아지면 그대로 쓰지 않고
// barHeight/2로 줄인다 — 그러지 않으면 짧은 막대가 타원처럼 보인다.
const BAR_CORNER_RADIUS = 2;
// 존재하지만 작은 값도 "칸이 비었다(결측)"와는 눈으로 구별돼야 한다 — 결측은 아예
// 그리지 않으므로, 존재하는 값은 아무리 작아도 이 높이만큼은 보이게 한다.
const MIN_BAR_HEIGHT = 4;

// band형(지방/철분)처럼 퍼센트 자체가 없는 영양소용 고정 마커. "막대의 축소판"으로
// 보이면 안 되므로, 어떤 막대보다도 낮고(MIN_BAR_HEIGHT보다 작음) 넓게(자기 칸의
// barWidth보다 항상 넓음), 양 끝이 완전히 둥근 알약(캡슐) 모양으로 그린다 — 막대는
// 모서리만 살짝 둥근 사각형이라 실루엣 자체가 다르다. 불투명도도 낮춰 한 번 더 구분한다.
const PILL_HEIGHT = 3;
const PILL_WIDTH_RATIO = 1.8; // barWidth 대비
const PILL_MAX_WIDTH_RATIO = 0.85; // columnWidth 대비 상한 — 옆 칸을 침범하지 않도록
const PILL_OPACITY = 0.45;

// 기준 대비 퍼센트 축 — mg/g/kcal처럼 단위가 다른 영양소를 한 축에 같이 그리기 위한
// 것일 뿐, 100%를 "넘으면 안 되는 선"으로 표시하지는 않는다(차트의 목적은 칸끼리
// 비교하는 것이지 기준 판정이 아니다 — 기준 판정은 아래 카드가 다른 기준으로 한다).
// 하한은 거의 비어 있는 기간에 축이 0에 가깝게 눌려 사소한 값이 꽉 찬 막대로
// 보이지 않도록 하는 최소한의 안전장치일 뿐, 특정 기준선을 위한 여유가 아니다.
// 상한 200은 OCR 오타 하나로 1000%가 나와도 다른 막대가 전부 바닥에 눌리지 않도록
// 막는다 — 이 상한을 넘는 막대는 축소하지 않고 위쪽에서 그대로 잘려 "차트를 벗어난다".
const AXIS_MIN = 10;
const AXIS_MAX_CAP = 200;
const AXIS_HEADROOM = 1.1;

type Props = {
  chart: ReportChart;
};

function isUnknown(nutrient: ReportChartNutrient) {
  return nutrient.tier === 'unknown';
}

function isFullyMissing(item: ReportChartItem, keys: string[]) {
  return keys.every((key) => isUnknown(item.nutrients[key]));
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <View style={styles.legendItem}>
      <View style={[styles.legendDot, { backgroundColor: color }]} />
      <Text style={styles.legendLabel}>{label}</Text>
    </View>
  );
}

/** 일간(4칸: 새벽/오전/오후/저녁)과 주간(7칸: 월~일) 모두 이 컴포넌트 하나로 그린다 —
 *  두 응답 모두 chart.items[]가 같은 모양이라 화면 쪽에서 분기할 이유가 없다.
 *
 *  영양소는 카페인 + 사용자가 고른 최대 3개(=최대 4개)까지 동적으로 온다. 서로 다른
 *  단위를 하나의 raw 축으로 비교할 수 없으므로 전부 "기준 대비 퍼센트"라는 단일 축을
 *  공유한다. 이 축은 어디까지나 칸끼리(요일별/시간대별) 서로 비교하기 위한 것이라
 *  100% 위치를 따로 표시하지 않는다 — 기준 초과 여부 판정은 아래 카드가 전담한다
 *  (특히 일간 차트는 버킷이 시간대라, 시간대 하나를 "하루 기준"과 견주는 건 애초에
 *  의미 있는 문턱이 아니다).
 *
 *  막대 채움색은 항상 영양소 정체성(nutrientColorFor) — 아래 nutrient_items 목록과
 *  같은 색이어야 "이 막대가 무슨 영양소인지"를 두 벌의 색 규칙 없이 알 수 있다.
 *  unknown은 아예 그리지 않는다. */
export default function IntakeTrendChart({ chart }: Props) {
  const [width, setWidth] = useState(0);
  const handleLayout = (event: LayoutChangeEvent) => setWidth(event.nativeEvent.layout.width);

  const items = chart.items;
  const nutrientKeys = Object.keys(items[0]?.nutrients ?? {});
  const allMissing =
    items.length === 0 ||
    nutrientKeys.length === 0 ||
    items.every((item) => isFullyMissing(item, nutrientKeys));

  if (allMissing) {
    return (
      <View style={styles.card}>
        <Text style={styles.title}>{chart.title}</Text>
        <View style={styles.emptyBox}>
          <Text style={styles.emptyText}>기록이 없어요</Text>
        </View>
      </View>
    );
  }

  const presentPct: number[] = [];
  for (const item of items) {
    for (const key of nutrientKeys) {
      const nutrient = item.nutrients[key];
      if (!isUnknown(nutrient) && nutrient.pct != null) {
        presentPct.push(nutrient.pct);
      }
    }
  }
  const axisMax = Math.min(AXIS_MAX_CAP, Math.max(AXIS_MIN, ...presentPct) * AXIS_HEADROOM);

  const columnWidth = width > 0 ? width / items.length : 0;
  const groupWidth = columnWidth * BAR_GROUP_WIDTH_RATIO;
  const n = nutrientKeys.length;
  const barWidth = n > 0 ? Math.max(0, (groupWidth - (n - 1) * BAR_GAP) / n) : 0;

  return (
    <View style={styles.card}>
      <Text style={styles.title}>{chart.title}</Text>

      <View style={styles.legendRow}>
        {nutrientKeys.map((key) => (
          <LegendDot
            key={key}
            color={nutrientColorFor(key).value}
            label={items[0].nutrients[key].label}
          />
        ))}
      </View>

      <View onLayout={handleLayout}>
        {width > 0 ? (
          <Svg width={width} height={PLOT_HEIGHT}>
            {items.map((item, index) => {
              const groupStartX = index * columnWidth + (columnWidth - groupWidth) / 2;
              return (
                <G key={item.date ?? `${item.label}-${index}`}>
                  {nutrientKeys.map((key, keyIndex) => {
                    const nutrient = item.nutrients[key];
                    if (isUnknown(nutrient)) return null;

                    const x = groupStartX + keyIndex * (barWidth + BAR_GAP);
                    const fill = nutrientColorFor(key).value;

                    if (nutrient.pct == null) {
                      // band형(지방/철분) — 값에 비례하지 않는 고정 마커. 자기 막대
                      // 칸(barWidth)보다 넓게, 어떤 막대보다 낮게, 양 끝을 완전히
                      // 둥글려(rx=height/2, 진짜 캡슐 모양) 그려서 "짧은 막대"로
                      // 오인되지 않게 한다. 칸 중심을 기준으로 좌우로 넓힌다.
                      const pillWidth = Math.min(
                        barWidth * PILL_WIDTH_RATIO,
                        columnWidth * PILL_MAX_WIDTH_RATIO
                      );
                      const pillX = x + barWidth / 2 - pillWidth / 2;
                      return (
                        <Rect
                          key={key}
                          x={pillX}
                          y={PLOT_HEIGHT - PILL_HEIGHT}
                          width={pillWidth}
                          height={PILL_HEIGHT}
                          rx={PILL_HEIGHT / 2}
                          fill={fill}
                          opacity={PILL_OPACITY}
                        />
                      );
                    }

                    const heightRatio = Math.min(nutrient.pct / axisMax, 1);
                    // 존재하는 값은 아무리 작아도 MIN_BAR_HEIGHT만큼은 보이게 한다 —
                    // 결측(아예 안 그림)과 "작지만 있는 값"이 눈으로 구별돼야 한다.
                    const barHeight = Math.max(MIN_BAR_HEIGHT, heightRatio * USABLE_HEIGHT);
                    // 모서리 반경이 막대 높이의 절반을 넘으면 짧은 막대가 타원처럼
                    // 보인다 — 높이에 맞춰 줄인다.
                    const barRadius = Math.min(BAR_CORNER_RADIUS, barHeight / 2);
                    return (
                      <Rect
                        key={key}
                        x={x}
                        y={PLOT_HEIGHT - barHeight}
                        width={barWidth}
                        height={barHeight}
                        rx={barRadius}
                        fill={fill}
                      />
                    );
                  })}
                </G>
              );
            })}
          </Svg>
        ) : (
          // width 측정 전에는 아무것도 그리지 않는다 — 0 너비로 그리면 막대 좌표가
          // 전부 0이 되어 한 줄로 찌그러진 차트가 잠깐 보인다.
          <View style={{ height: PLOT_HEIGHT }} />
        )}
      </View>

      <View style={styles.labelRow}>
        {items.map((item, index) => (
          <Text key={item.date ?? `${item.label}-${index}`} style={styles.axisLabel}>
            {item.label}
          </Text>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 15,
    borderWidth: 0.7,
    borderColor: authColors.border,
    backgroundColor: authColors.white,
    paddingHorizontal: 16,
    paddingVertical: 20,
  },
  title: {
    fontFamily: fonts.semiBold,
    fontSize: 14,
    color: authColors.brown,
    marginBottom: 12,
  },
  legendRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 16,
    marginBottom: 12,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  legendDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  legendLabel: {
    fontFamily: fonts.medium,
    fontSize: 11,
    color: authColors.gray,
  },
  labelRow: {
    flexDirection: 'row',
    marginTop: 6,
  },
  axisLabel: {
    flex: 1,
    textAlign: 'center',
    fontFamily: fonts.medium,
    fontSize: 11,
    color: authColors.gray,
  },
  emptyBox: {
    height: PLOT_HEIGHT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyText: {
    fontFamily: fonts.medium,
    fontSize: 13,
    color: authColors.gray,
  },
});
