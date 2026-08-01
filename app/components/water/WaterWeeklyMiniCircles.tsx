import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, Text, View } from 'react-native';
import Svg, { Circle, ClipPath, Defs, Rect } from 'react-native-svg';

import { authColors } from '@/components/auth/colors';
import { waterColors } from '@/components/water/colors';
import { fonts } from '@/constants/fonts';
import { WaterWeekDay } from '@/lib/api-client';

// 막대+마커의 "이중 계산" 구조에서 계속 어긋남이 발생했던 문제를 근본적으로
// 없애기 위해, 막대 대신 요일별로 작은 원형 게이지를 쓴다. 각 원은 고정
// 크기(size)이고, 그 안의 채움 정도만 percent로 달라진다 - WaterWaveCircle과
// 달리 파도 애니메이션 없이 정적인 사각형 채움만 그린다(반복 렌더링/Reanimated
// 불필요). 100% 채움 자체가 목표 달성 표시라서 별도의 기준선 개념이 없다.
function MiniCircle({ day, targetMl, size }: { day: WaterWeekDay; targetMl: number; size: number }) {
  const percent = targetMl > 0 ? Math.min(100, (day.amount_ml / targetMl) * 100) : 0;
  const fillHeight = (percent / 100) * size;
  const clipId = `waterMiniClip-${day.date}`;
  const strokeWidth = 1.5;

  return (
    <View style={{ width: size, height: size }}>
      <Svg width={size} height={size}>
        <Defs>
          <ClipPath id={clipId}>
            <Circle cx={size / 2} cy={size / 2} r={size / 2} />
          </ClipPath>
        </Defs>

        <Circle cx={size / 2} cy={size / 2} r={size / 2} fill={waterColors.track} />

        {fillHeight > 0 && (
          <Rect
            x={0}
            y={size - fillHeight}
            width={size}
            height={fillHeight}
            fill={waterColors.miniCircleFill}
            clipPath={`url(#${clipId})`}
          />
        )}

        <Circle
          cx={size / 2}
          cy={size / 2}
          r={size / 2 - strokeWidth / 2}
          stroke={authColors.border}
          strokeWidth={strokeWidth}
          fill="none"
        />
      </Svg>

      {day.hit_target && (
        <View style={styles.checkOverlay} pointerEvents="none">
          <Ionicons name="checkmark" size={Math.max(12, size * 0.4)} color={authColors.white} />
        </View>
      )}
    </View>
  );
}

type WaterWeeklyMiniCirclesProps = {
  days: WaterWeekDay[];
  targetMl: number;
  size?: number;
};

export default function WaterWeeklyMiniCircles({ days, targetMl, size = 38 }: WaterWeeklyMiniCirclesProps) {
  return (
    <View style={styles.row}>
      {days.map((day) => (
        <View key={day.date} style={styles.column}>
          <MiniCircle day={day} targetMl={targetMl} size={size} />
          <Text style={[styles.dayLabel, day.is_today && styles.dayLabelToday]}>{day.label}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  column: {
    alignItems: 'center',
  },
  checkOverlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dayLabel: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
    marginTop: 6,
  },
  dayLabelToday: {
    fontFamily: fonts.semiBold,
    color: authColors.brown,
    textDecorationLine: 'underline',
  },
});
