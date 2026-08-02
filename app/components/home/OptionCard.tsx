import { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';

import { authColors } from '@/components/auth/colors';
import { fonts, nanumSquareRound } from '@/constants/fonts';

export default function OptionCard({
  icon,
  label,
  description,
  onPress,
}: {
  icon: ReactNode;
  label: string;
  description: string;
  onPress: () => void;
}) {
  const scale = useSharedValue(1);

  const cardStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  return (
    <Pressable
      style={styles.optionButton}
      onPress={onPress}
      onPressIn={() => {
        scale.value = withTiming(0.97, { duration: 90 });
      }}
      onPressOut={() => {
        scale.value = withTiming(1, { duration: 90 });
      }}>
      <Animated.View style={cardStyle}>
        <View style={styles.optionIconWrap}>{icon}</View>
        <Text style={styles.optionLabel}>{label}</Text>
        <Text style={styles.optionDesc}>{description}</Text>
      </Animated.View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  optionButton: {
    flex: 1,
    backgroundColor: '#FFF5F3',
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 18,
    paddingVertical: 12,
    paddingHorizontal: 4,
    alignItems: 'center',
  },
  optionIconWrap: {
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },
  optionLabel: {
    fontFamily: fonts.medium,
    fontSize: 14,
    color: '#000000',
    textAlign: 'center',
    marginTop: 8,
  },
  optionDesc: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 11,
    color: authColors.gray,
    textAlign: 'center',
    marginTop: 4,
  },
});
