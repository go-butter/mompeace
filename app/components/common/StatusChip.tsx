import { StyleProp, StyleSheet, Text, View, ViewStyle } from 'react-native';

import { fonts } from '@/constants/fonts';

export default function StatusChip({
  label,
  value,
  colors,
  style,
}: {
  label: string;
  value: string;
  colors: { label: string; value: string; bg: string };
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <View style={[styles.chip, { backgroundColor: colors.bg }, style]}>
      <Text style={[styles.chipLabel, { color: colors.label }]}>{label}</Text>
      <Text style={[styles.chipValue, { color: colors.value }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    flex: 1,
    borderRadius: 12,
    paddingVertical: 10,
    alignItems: 'center',
  },
  chipLabel: {
    fontFamily: fonts.regular,
    fontSize: 11,
  },
  chipValue: {
    fontFamily: fonts.bold,
    fontSize: 13,
    marginTop: 4,
  },
});
