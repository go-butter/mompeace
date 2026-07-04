import { Pressable, StyleSheet, Text } from 'react-native';
import Animated, { useAnimatedStyle, withSpring } from 'react-native-reanimated';

import { authColors } from '@/components/auth/colors';
import { fonts } from '@/constants/fonts';

const TOGGLE_SPRING_CONFIG = { damping: 18, stiffness: 180, overshootClamping: true };
const TRACK_WIDTH = 58;
const TRACK_HEIGHT = 32;
const THUMB_SIZE = 28;
const THUMB_INSET = 2;
const THUMB_TRAVEL = TRACK_WIDTH - THUMB_INSET * 2 - THUMB_SIZE;

export function PremiumToggle({ value, onToggle }: { value: boolean; onToggle: () => void }) {
  const trackStyle = useAnimatedStyle(() => ({
    backgroundColor: withSpring(value ? authColors.pink : '#E4E4E4', TOGGLE_SPRING_CONFIG),
  }));
  const thumbStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: withSpring(value ? THUMB_TRAVEL : 0, TOGGLE_SPRING_CONFIG) }],
  }));

  return (
    <Pressable onPress={onToggle} hitSlop={8}>
      <Animated.View style={[styles.track, trackStyle]}>
        <Text style={[styles.label, styles.labelOn]}>ON</Text>
        <Text style={[styles.label, styles.labelOff]}>OFF</Text>
        <Animated.View style={[styles.thumb, thumbStyle]} />
      </Animated.View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  track: {
    width: TRACK_WIDTH,
    height: TRACK_HEIGHT,
    borderRadius: TRACK_HEIGHT / 2,
    overflow: 'hidden',
  },
  thumb: {
    position: 'absolute',
    top: THUMB_INSET,
    left: THUMB_INSET,
    width: THUMB_SIZE,
    height: THUMB_SIZE,
    borderRadius: THUMB_SIZE / 2,
    backgroundColor: authColors.white,
  },
  label: {
    position: 'absolute',
    top: 0,
    height: TRACK_HEIGHT,
    lineHeight: TRACK_HEIGHT,
    fontFamily: fonts.bold,
    fontSize: 10,
  },
  labelOn: {
    left: 8,
    color: 'rgba(255,255,255,0.55)',
  },
  labelOff: {
    right: 7,
    color: 'rgba(0,0,0,0.2)',
  },
});
