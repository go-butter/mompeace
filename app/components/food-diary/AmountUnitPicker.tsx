import { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import ChevronDownIcon from '@/assets/images/common/chevron_down_plain.svg';
import { authColors } from '@/components/auth/colors';
import BottomSheet from '@/components/common/BottomSheet';
import { fonts, nanumSquareRound } from '@/constants/fonts';

export const UNITS = ['개', '인분', '접시', '컵', 'g', 'ml'];
export const WEIGHT_UNITS = ['g', 'ml'];
const AMOUNT_PRESETS = [
  { label: '1/4', value: '0.25' },
  { label: '1/3', value: '0.33' },
  { label: '1/2', value: '0.5' },
  { label: '1', value: '1' },
  { label: '2', value: '2' },
];

function sanitizeNonNegativeDecimal(text: string) {
  const digitsAndDot = text.replace(/[^0-9.]/g, '');
  const firstDotIndex = digitsAndDot.indexOf('.');
  if (firstDotIndex === -1) return digitsAndDot;
  return (
    digitsAndDot.slice(0, firstDotIndex + 1) +
    digitsAndDot.slice(firstDotIndex + 1).replace(/\./g, '')
  );
}

function sanitizeIntegerServings(text: string) {
  return text.replace(/[^0-9]/g, '');
}

// 인분은 부분 인분 로깅을 지원하지 않음 — 소수/0 이하는 그램 단위를 쓰도록 유도한다
// (앱 전체에서 "0.5인분" 같은 값은 저장하지 않음).
function sanitizeForUnit(text: string, unit: string) {
  return unit === '인분' ? sanitizeIntegerServings(text) : sanitizeNonNegativeDecimal(text);
}

export default function AmountUnitPicker({
  amount,
  unit,
  onChangeAmount,
  onChangeUnit,
}: {
  amount: string;
  unit: string;
  onChangeAmount: (next: string) => void;
  onChangeUnit: (next: string) => void;
}) {
  const insets = useSafeAreaInsets();
  const [unitSheetVisible, setUnitSheetVisible] = useState(false);

  const selectUnit = (nextUnit: string) => {
    onChangeUnit(nextUnit);
    setUnitSheetVisible(false);
    if (nextUnit === '인분') {
      const current = Number(amount);
      if (!Number.isInteger(current) || current < 1) {
        onChangeAmount('1');
      }
    }
  };

  return (
    <>
      <View style={styles.presetRow}>
        {AMOUNT_PRESETS.map((p) => (
          <Pressable
            key={p.label}
            style={[styles.presetChip, amount === p.value && styles.presetChipSelected]}
            onPress={() => onChangeAmount(sanitizeForUnit(p.value, unit))}>
            <Text
              style={[
                styles.presetChipText,
                amount === p.value && styles.presetChipTextSelected,
              ]}>
              {p.label}
            </Text>
          </Pressable>
        ))}
      </View>
      <View style={styles.amountRow}>
        <TextInput
          style={styles.amountInput}
          value={amount}
          onChangeText={(text) => onChangeAmount(sanitizeForUnit(text, unit))}
          keyboardType={unit === '인분' ? 'number-pad' : 'numeric'}
        />
        <Pressable style={styles.unitTriggerPill} onPress={() => setUnitSheetVisible(true)}>
          <Text style={styles.unitTriggerPillText}>{unit}</Text>
          <ChevronDownIcon width={12} height={8} />
        </Pressable>
      </View>

      <BottomSheet visible={unitSheetVisible} onClose={() => setUnitSheetVisible(false)}>
        <View style={[styles.sheetContainer, { paddingBottom: styles.sheetContainer.paddingBottom + insets.bottom }]}>
          <Text style={styles.sheetTitle}>섭취단위 선택</Text>
          {UNITS.map((u) => (
            <Pressable
              key={u}
              style={[styles.unitRow, unit === u && styles.unitRowSelected]}
              onPress={() => selectUnit(u)}>
              <Text style={[styles.unitRowText, unit === u && styles.unitRowTextSelected]}>
                {u}
              </Text>
            </Pressable>
          ))}
          <Pressable onPress={() => setUnitSheetVisible(false)}>
            <Text style={styles.sheetCancelText}>닫기</Text>
          </Pressable>
        </View>
      </BottomSheet>
    </>
  );
}

const styles = StyleSheet.create({
  presetRow: {
    flexDirection: 'row',
    gap: 6,
    marginTop: 10,
  },
  presetChip: {
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 100,
    paddingHorizontal: 16,
    paddingVertical: 7,
    backgroundColor: '#FFF5F3',
  },
  presetChipSelected: {
    borderColor: authColors.pink,
    backgroundColor: authColors.pink,
  },
  presetChipText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 11,
    color: authColors.gray,
  },
  presetChipTextSelected: {
    color: authColors.white,
  },
  amountRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 10,
    gap: 8,
  },
  amountInput: {
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    height: 32,
    flex: 1,
    paddingHorizontal: 12,
    fontSize: 12,
    color: '#000000',
  },
  unitTriggerPill: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    backgroundColor: '#FFF5F3',
    flexShrink: 0,
    height: 32,
    paddingHorizontal: 12,
  },
  unitTriggerPillText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 12,
    color: authColors.gray,
  },
  sheetContainer: {
    backgroundColor: authColors.white,
    borderTopLeftRadius: 30,
    borderTopRightRadius: 30,
    paddingTop: 36,
    paddingHorizontal: 19,
    paddingBottom: 40,
  },
  sheetTitle: {
    fontFamily: fonts.medium,
    fontSize: 18,
    color: '#000000',
    marginBottom: 8,
  },
  unitRow: {
    paddingVertical: 14,
    borderBottomWidth: 0.7,
    borderBottomColor: authColors.border,
  },
  unitRowSelected: {
    backgroundColor: '#FFF5F3',
    borderRadius: 6,
    paddingHorizontal: 8,
  },
  unitRowText: {
    fontFamily: fonts.medium,
    fontSize: 15,
    color: authColors.grayDark,
  },
  unitRowTextSelected: {
    color: authColors.pink,
  },
  sheetCancelText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 15,
    color: authColors.gray,
    textAlign: 'center',
    marginTop: 16,
    textDecorationLine: 'underline',
  },
});
