import { Pressable, StyleSheet, Text, View } from 'react-native';

import { authColors } from '@/components/auth/colors';
import { fonts } from '@/constants/fonts';
import {
  MAX_SELECTED_NUTRIENTS,
  NUTRIENT_LABELS_KO,
  SELECTABLE_NUTRIENT_KEYS,
  SelectableNutrientKey,
} from '@/constants/nutrients';

export function NutrientPicker({
  selected,
  onChange,
  max = MAX_SELECTED_NUTRIENTS,
}: {
  selected: SelectableNutrientKey[];
  onChange: (next: SelectableNutrientKey[]) => void;
  max?: number;
}) {
  const toggle = (key: SelectableNutrientKey) => {
    if (selected.includes(key)) {
      onChange(selected.filter((k) => k !== key));
      return;
    }
    if (selected.length >= max) {
      return;
    }
    onChange([...selected, key]);
  };

  return (
    <View style={styles.wrap}>
      {SELECTABLE_NUTRIENT_KEYS.map((key) => {
        const isSelected = selected.includes(key);
        const isDisabled = !isSelected && selected.length >= max;
        return (
          <Pressable
            key={key}
            onPress={() => toggle(key)}
            disabled={isDisabled}
            style={[
              styles.chip,
              isSelected && styles.chipSelected,
              isDisabled && styles.chipDisabled,
            ]}>
            <Text
              style={[
                styles.chipText,
                isSelected && styles.chipTextSelected,
                isDisabled && styles.chipTextDisabled,
              ]}>
              {NUTRIENT_LABELS_KO[key]}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  chip: {
    borderWidth: 1,
    borderColor: authColors.border,
    backgroundColor: authColors.white,
    borderRadius: 999,
    paddingHorizontal: 18,
    paddingVertical: 10,
  },
  chipSelected: {
    // 원래 authColors.pink는 배경으로 쓰기엔 채도가 너무 높아, 같은 색 계열의
    // 옅은 톤으로 완화 (전역 authColors는 버튼 등 다른 곳에서 진한 톤 그대로 써야 하므로
    // 여기서만 로컬로 옅게 만든 값을 사용한다).
    backgroundColor: '#FBD9DD',
    borderColor: '#FBD9DD',
  },
  chipDisabled: {
    opacity: 0.4,
  },
  chipText: {
    fontSize: 14,
    fontFamily: fonts.medium,
    color: authColors.brown,
  },
  chipTextSelected: {
    color: authColors.pink,
  },
  chipTextDisabled: {
    color: authColors.gray,
  },
});
