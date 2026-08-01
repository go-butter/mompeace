import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useId, useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, {
  Easing,
  cancelAnimation,
  useAnimatedProps,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Circle, ClipPath, Defs, G, Path } from 'react-native-svg';

import { authColors } from '@/components/auth/colors';
import { waterColors } from '@/components/water/colors';
import { fonts } from '@/constants/fonts';

const AnimatedPath = Animated.createAnimatedComponent(Path);

// 원 지름(waveWidth)과 동일한 파장 1주기짜리 웨이브 경로를 만든다. 이 d 문자열은
// 절대 매 프레임 다시 만들지 않는다 - 애니메이션은 Path의 transform(translateX/Y)만
// useAnimatedProps로 갱신한다. 같은 경로를 waveWidth만큼 옆으로 옮긴 사본과 함께
// 반복 이동시키면 이음매 없이 루프된다.
function buildWavePath(waveWidth: number, waveHeight: number, amplitude: number) {
  const points: string[] = [];
  const step = 4;
  for (let x = 0; x <= waveWidth; x += step) {
    const y = amplitude * Math.sin((x / waveWidth) * Math.PI * 2);
    points.push(`${x === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(2)}`);
  }
  points.push(`L${waveWidth} ${waveHeight}`);
  points.push(`L0 ${waveHeight}`);
  points.push('Z');
  return points.join(' ');
}

type WaterWaveCircleProps = {
  percent: number;
  size?: number;
  currentMl?: number;
  targetMl?: number;
  showLabel?: boolean;
};

export default function WaterWaveCircle({
  percent,
  size = 200,
  currentMl,
  targetMl,
  showLabel = true,
}: WaterWaveCircleProps) {
  const clampedPercent = Math.max(0, Math.min(percent, 100));
  const strokeWidth = 3;
  const amplitude = size * 0.035;
  // clipPath id가 겹치면 iOS RNSVG에서 클리핑이 통째로 안 먹는 경우가 있어
  // 인스턴스마다 고유 id를 쓴다 (영숫자만 남겨 url(#...) 참조 안전성 확보).
  const clipId = `waterWaveClip${useId().replace(/[^a-zA-Z0-9]/g, '')}`;

  const frontWaveD = useMemo(() => buildWavePath(size, size, amplitude), [size, amplitude]);
  const backWaveD = useMemo(() => buildWavePath(size, size, amplitude * 1.2), [size, amplitude]);

  const fillLevel = useSharedValue(clampedPercent);
  const frontPhase = useSharedValue(0);
  const backPhase = useSharedValue(size * 0.5);

  // 수위(percent)가 바뀔 때만 한 번 전환 - 매 프레임 비용 아님.
  useEffect(() => {
    fillLevel.value = withTiming(clampedPercent, { duration: 600 });
  }, [clampedPercent, fillLevel]);

  // 화면을 벗어나면(blur) 루프 애니메이션을 멈춰 불필요한 배터리 소모를 막는다.
  useFocusEffect(
    useCallback(() => {
      frontPhase.value = 0;
      frontPhase.value = withRepeat(
        withTiming(-size, { duration: 2800, easing: Easing.linear }),
        -1,
        false
      );
      backPhase.value = size * 0.5;
      backPhase.value = withRepeat(
        withTiming(-size * 0.5, { duration: 4200, easing: Easing.linear }),
        -1,
        false
      );

      return () => {
        cancelAnimation(frontPhase);
        cancelAnimation(backPhase);
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [size])
  );

  // G(그룹)를 useAnimatedProps로 감싸는 대신, 리프 요소인 Path 4장 각각에
  // transform 배열을 직접 애니메이션한다. RNSVG에서 그룹(G)을 Animated로
  // 감싸는 조합은 iOS(특히 Fabric)에서 자식이 아예 렌더되지 않는 경우가
  // 보고되어 있고, transform 배열 형태가 x/y 단축 prop보다 더 안정적으로
  // 지원된다 - 두 이유로 리프 레벨 + transform 배열 방식을 쓴다.
  const frontPrimaryProps = useAnimatedProps(() => ({
    transform: [
      { translateY: size - (fillLevel.value / 100) * size },
      { translateX: frontPhase.value },
    ],
  }));
  const frontSecondaryProps = useAnimatedProps(() => ({
    transform: [
      { translateY: size - (fillLevel.value / 100) * size },
      { translateX: frontPhase.value + size },
    ],
  }));
  const backPrimaryProps = useAnimatedProps(() => ({
    transform: [
      { translateY: size - (fillLevel.value / 100) * size },
      { translateX: backPhase.value },
    ],
  }));
  const backSecondaryProps = useAnimatedProps(() => ({
    transform: [
      { translateY: size - (fillLevel.value / 100) * size },
      { translateX: backPhase.value + size },
    ],
  }));

  return (
    <View style={{ width: size, height: size }}>
      <Svg width={size} height={size}>
        <Defs>
          <ClipPath id={clipId}>
            <Circle cx={size / 2} cy={size / 2} r={size / 2} />
          </ClipPath>
        </Defs>

        <Circle cx={size / 2} cy={size / 2} r={size / 2} fill={waterColors.track} />

        <G clipPath={`url(#${clipId})`}>
          <AnimatedPath
            d={backWaveD}
            fill={waterColors.waveBack}
            fillOpacity={0.55}
            animatedProps={backPrimaryProps}
          />
          <AnimatedPath
            d={backWaveD}
            fill={waterColors.waveBack}
            fillOpacity={0.55}
            animatedProps={backSecondaryProps}
          />
          <AnimatedPath d={frontWaveD} fill={waterColors.waveFront} animatedProps={frontPrimaryProps} />
          <AnimatedPath d={frontWaveD} fill={waterColors.waveFront} animatedProps={frontSecondaryProps} />
        </G>

        <Circle
          cx={size / 2}
          cy={size / 2}
          r={size / 2 - strokeWidth / 2}
          stroke={authColors.border}
          strokeWidth={strokeWidth}
          fill="none"
        />
      </Svg>

      {showLabel && (
        <View style={styles.labelOverlay} pointerEvents="none">
          <Text style={styles.mlValue}>{Math.round(currentMl ?? 0)}</Text>
          <Text style={styles.mlUnit}>/ {Math.round(targetMl ?? 0)}ml</Text>
          <Text style={styles.percentText}>{Math.round(percent)}%</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  labelOverlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
  },
  mlValue: {
    fontFamily: fonts.bold,
    fontSize: 32,
    color: authColors.brown,
  },
  mlUnit: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
    marginTop: 2,
  },
  percentText: {
    fontFamily: fonts.semiBold,
    fontSize: 14,
    color: authColors.brown,
    marginTop: 6,
  },
});
