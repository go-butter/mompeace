import { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Circle, G, Rect, Text as SvgText } from 'react-native-svg';
import {
  VictoryAxis,
  VictoryBar,
  VictoryChart,
  VictoryLabel,
  VictoryLine,
  VictoryScatter,
  VictoryTooltip,
  VictoryVoronoiContainer,
} from 'victory-native';

import { fonts } from '@/constants/fonts';
import type { PremiumReportDailyChartItem, PremiumReportWeeklyChartItem } from '@/lib/api-client';
import { nutrientColors, referenceLineColor, statusColors } from './colors';

type ChartItem = PremiumReportDailyChartItem | PremiumReportWeeklyChartItem;
type NutrientKey = 'caffeine' | 'sugar' | 'sodium';

interface ChartPoint {
  x: string;
  y: number;
  unknown: boolean;
  rawValue: number;
  rawUnit: string;
}

interface IntakeChartProps {
  items: ChartItem[];
}

const CHART_HEIGHT = 240;
const REFERENCE_PCT = 100;

const rawFieldByNutrient: Record<NutrientKey, keyof ChartItem> = {
  caffeine: 'caffeine_mg',
  sugar: 'sugar_g',
  sodium: 'sodium_mg',
};
const pctFieldByNutrient: Record<NutrientKey, keyof ChartItem> = {
  caffeine: 'caffeine_pct',
  sugar: 'sugar_pct',
  sodium: 'sodium_pct',
};
const statusFieldByNutrient: Record<NutrientKey, keyof ChartItem> = {
  caffeine: 'caffeine_status',
  sugar: 'sugar_status',
  sodium: 'sodium_status',
};
const unitByNutrient: Record<NutrientKey, string> = {
  caffeine: 'mg',
  sugar: 'g',
  sodium: 'mg',
};

function toPoints(items: ChartItem[], nutrient: NutrientKey): ChartPoint[] {
  return items.map((item) => ({
    x: item.label,
    y: Number(item[pctFieldByNutrient[nutrient]]),
    unknown: item[statusFieldByNutrient[nutrient]] === 'unknown',
    rawValue: Number(item[rawFieldByNutrient[nutrient]]),
    rawUnit: unitByNutrient[nutrient],
  }));
}

function UnknownAwareBar(props: any) {
  const { x, y, y0, width = 14, datum } = props;
  if (!datum?.unknown) {
    return <Rect x={x - width / 2} y={y} width={width} height={Math.max(y0 - y, 0)} fill={nutrientColors.sugar} rx={3} />;
  }
  const barHeight = 16;
  return (
    <G>
      <Rect
        x={x - width / 2}
        y={y0 - barHeight}
        width={width}
        height={barHeight}
        fill="#F1F1F1"
        stroke={statusColors.unknown}
        strokeDasharray="3,3"
        rx={3}
      />
      <SvgText x={x} y={y0 - barHeight / 2 + 4} fontSize={10} fill={statusColors.unknown} textAnchor="middle">
        ?
      </SvgText>
    </G>
  );
}

function UnknownAwarePoint(props: any) {
  const { x, y, datum, color } = props;
  if (datum?.unknown) {
    return (
      <G>
        <Circle cx={x} cy={y} r={7} fill="#F1F1F1" stroke={statusColors.unknown} strokeDasharray="2,2" />
        <SvgText x={x} y={y + 3} fontSize={8} fill={statusColors.unknown} textAnchor="middle">
          ?
        </SvgText>
      </G>
    );
  }
  return <Circle cx={x} cy={y} r={3.5} fill={color} />;
}

export default function IntakeChart({ items }: IntakeChartProps) {
  const sugarData = useMemo(() => toPoints(items, 'sugar'), [items]);
  const caffeineData = useMemo(() => toPoints(items, 'caffeine'), [items]);
  const sodiumData = useMemo(() => toPoints(items, 'sodium'), [items]);
  const referenceData = useMemo(
    () => items.map((item) => ({ x: item.label, y: REFERENCE_PCT })),
    [items]
  );

  return (
    <View style={styles.container}>
      <VictoryChart
        height={CHART_HEIGHT}
        domain={{ y: [0, 150] }}
        domainPadding={{ x: 20 }}
        containerComponent={
          <VictoryVoronoiContainer
            voronoiDimension="x"
            labels={({ datum }: any) => `${datum.rawValue}${datum.rawUnit}`}
            labelComponent={
              <VictoryTooltip
                style={{ fontFamily: fonts.medium, fontSize: 11, fill: '#6A3A25' }}
                flyoutStyle={{ stroke: '#ECDEDD', fill: '#FFFFFF' }}
              />
            }
          />
        }>
        <VictoryAxis
          style={{
            axis: { stroke: '#ECDEDD' },
            tickLabels: { fontFamily: fonts.regular, fontSize: 10, fill: '#67677A' },
          }}
        />
        <VictoryAxis
          dependentAxis
          tickValues={[0, 50, 100, 150]}
          tickFormat={(t: number) => `${t}%`}
          style={{
            axis: { stroke: 'transparent' },
            grid: { stroke: '#F5F0EE' },
            tickLabels: { fontFamily: fonts.regular, fontSize: 9, fill: '#67677A' },
          }}
        />

        <VictoryBar data={sugarData} barWidth={14} dataComponent={<UnknownAwareBar />} />

        <VictoryLine data={caffeineData} style={{ data: { stroke: nutrientColors.caffeine, strokeWidth: 2 } }} />
        <VictoryScatter data={caffeineData} dataComponent={<UnknownAwarePoint color={nutrientColors.caffeine} />} />

        <VictoryLine data={sodiumData} style={{ data: { stroke: nutrientColors.sodium, strokeWidth: 2 } }} />
        <VictoryScatter data={sodiumData} dataComponent={<UnknownAwarePoint color={nutrientColors.sodium} />} />

        <VictoryLine
          data={referenceData}
          style={{ data: { stroke: referenceLineColor, strokeWidth: 1.5, strokeDasharray: '6,4' } }}
          labels={({ index }: any) => (Number(index) === referenceData.length - 1 ? '권장 기준' : '')}
          labelComponent={
            <VictoryLabel
              dx={-4}
              dy={-8}
              textAnchor="end"
              style={{ fontFamily: fonts.medium, fontSize: 10, fill: referenceLineColor }}
            />
          }
        />
      </VictoryChart>

      <View style={styles.legendRow}>
        <LegendItem color={nutrientColors.caffeine} label="카페인" shape="line" />
        <LegendItem color={nutrientColors.sugar} label="당류" shape="bar" />
        <LegendItem color={nutrientColors.sodium} label="나트륨" shape="line" />
        <LegendItem color={statusColors.unknown} label="정보 없음" shape="unknown" />
      </View>
    </View>
  );
}

function LegendItem({ color, label, shape }: { color: string; label: string; shape: 'line' | 'bar' | 'unknown' }) {
  return (
    <View style={styles.legendItem}>
      {shape === 'bar' ? (
        <View style={[styles.legendSwatchBar, { backgroundColor: color }]} />
      ) : shape === 'unknown' ? (
        <View style={[styles.legendSwatchDot, { borderColor: color, backgroundColor: '#F1F1F1' }]} />
      ) : (
        <View style={[styles.legendSwatchLine, { backgroundColor: color }]} />
      )}
      <Text style={styles.legendLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginTop: 8,
  },
  legendRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: 14,
    marginTop: 4,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  legendSwatchLine: {
    width: 12,
    height: 3,
    borderRadius: 1.5,
  },
  legendSwatchBar: {
    width: 10,
    height: 10,
    borderRadius: 2,
  },
  legendSwatchDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    borderWidth: 1,
    borderStyle: 'dashed' as any,
  },
  legendLabel: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: '#67677A',
  },
});
