import { StyleSheet, View } from 'react-native';

import { authColors } from '@/components/auth/colors';

export function StepProgressDots({
  activeStep,
  totalSteps = 2,
}: {
  activeStep: number;
  totalSteps?: number;
}) {
  return (
    <View style={styles.row}>
      {Array.from({ length: totalSteps }).map((_, i) => (
        <View
          key={i}
          style={[styles.dot, i + 1 === activeStep ? styles.dotActive : styles.dotInactive]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap: 10,
  },
  dot: {
    width: 12,
    height: 12,
    borderRadius: 6,
  },
  dotActive: {
    backgroundColor: authColors.pink,
  },
  dotInactive: {
    backgroundColor: authColors.border,
  },
});
