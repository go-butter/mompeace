import type { FC } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { SvgProps } from 'react-native-svg';

import { authColors } from '@/components/auth/colors';
import { fonts } from '@/constants/fonts';
import type { NutrientStatus } from '@/lib/api-client';
import { nutrientColors, referenceLineColor, statusLabel } from './colors';

export type NutrientKey = 'caffeine' | 'sugar' | 'sodium';

const increaseColor = referenceLineColor;
const decreaseColor = '#3B82C4';

interface MetricCardProps {
  nutrient: NutrientKey;
  label: string;
  Icon: FC<SvgProps>;
  value: number;
  unit: string;
  limit: number;
  pct: number;
  status: NutrientStatus;
  // undefined = daily card (no comparison row); null = weekly card but no confirmed prior data
  comparisonPct?: number | null;
}

export default function MetricCard({
  nutrient,
  label,
  Icon,
  value,
  unit,
  limit,
  pct,
  status,
  comparisonPct,
}: MetricCardProps) {
  const color = nutrientColors[nutrient];
  const isUnknown = status === 'unknown';
  const clampedPct = Math.min(Math.max(pct, 0), 100);

  return (
    <View style={styles.card}>
      <View style={styles.topRow}>
        <View style={styles.labelGroup}>
          <Icon width={16} height={16} />
          <Text style={styles.label}>{label}</Text>
        </View>
        <View style={styles.pctGroup}>
          <Text style={styles.pctLabel}>권장 기준 대비</Text>
          <Text style={[styles.pctValue, { color: isUnknown ? authColors.gray : color }]}>
            {isUnknown ? statusLabel.unknown : `${pct}%`}
          </Text>
        </View>
      </View>

      {isUnknown ? (
        <Text style={styles.unknownText}>기록된 섭취 정보가 없어요.</Text>
      ) : (
        <>
          <Text style={styles.valueWrapper}>
            <Text style={[styles.valueNumber, { color }]}>{value}</Text>
            <Text style={styles.valueUnit}>
              {' '}
              / {limit}
              {unit}
            </Text>
          </Text>
          <View style={styles.progressRow}>
            <View style={styles.progressTrack}>
              <View style={[styles.progressFill, { width: `${clampedPct}%`, backgroundColor: color }]} />
            </View>
            <Text style={styles.progressPct}>{pct}%</Text>
          </View>
        </>
      )}

      {comparisonPct !== undefined && (
        <View style={styles.comparisonRow}>
          <Text style={styles.comparisonLabel}>지난주 대비</Text>
          {comparisonPct === null ? (
            <Text style={styles.comparisonNone}>비교 데이터 없음</Text>
          ) : (
            <Text
              style={[
                styles.comparisonValue,
                { color: comparisonPct > 0 ? increaseColor : comparisonPct < 0 ? decreaseColor : authColors.gray },
              ]}>
              {comparisonPct > 0 ? '▲' : comparisonPct < 0 ? '▼' : '–'} {Math.abs(comparisonPct)}%p
            </Text>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: authColors.white,
    borderRadius: 20,
    padding: 16,
    shadowColor: '#FFEEF0',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 12,
    elevation: 4,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  labelGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  label: {
    fontFamily: fonts.medium,
    fontSize: 14,
    color: authColors.brown,
  },
  pctGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  pctLabel: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: authColors.gray,
  },
  pctValue: {
    fontFamily: fonts.bold,
    fontSize: 15,
  },
  unknownText: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: authColors.gray,
    marginTop: 12,
  },
  valueWrapper: {
    marginTop: 8,
  },
  valueNumber: {
    fontFamily: fonts.bold,
    fontSize: 24,
  },
  valueUnit: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
  },
  progressRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 6,
  },
  progressTrack: {
    flex: 1,
    height: 6,
    backgroundColor: authColors.border,
    borderRadius: 3,
    overflow: 'hidden',
  },
  progressFill: {
    height: 6,
    borderRadius: 3,
  },
  progressPct: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
  },
  comparisonRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 10,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: authColors.border,
  },
  comparisonLabel: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: authColors.gray,
  },
  comparisonValue: {
    fontFamily: fonts.semiBold,
    fontSize: 13,
  },
  comparisonNone: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: authColors.gray,
  },
});
