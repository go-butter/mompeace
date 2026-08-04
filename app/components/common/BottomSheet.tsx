import { ReactNode, useEffect, useState } from 'react';
import { Dimensions, Modal, Pressable, StyleSheet, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import Animated, {
  interpolate,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
} from 'react-native-reanimated';

const SCREEN_HEIGHT = Dimensions.get('window').height;
const ENTER_SPRING_CONFIG = { damping: 20, stiffness: 90, mass: 1 };
const EXIT_SPRING_CONFIG = { damping: 22, stiffness: 60, mass: 1.2 };

export default function BottomSheet({
  visible,
  onClose,
  children,
}: {
  visible: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  const [internalVisible, setInternalVisible] = useState(visible);
  const progress = useSharedValue(0);

  // Fully driven by the `visible` prop, in both directions: this lets a consumer
  // close the sheet either via backdrop tap (which calls onClose()) or by flipping
  // its own `visible` state directly (e.g. before navigating away) — either path
  // ends up here and plays the same exit animation before the Modal unmounts.
  useEffect(() => {
    if (visible) {
      setInternalVisible(true);
      progress.value = withSpring(1, ENTER_SPRING_CONFIG);
    } else {
      progress.value = withSpring(0, EXIT_SPRING_CONFIG, (finished) => {
        if (finished) {
          runOnJS(setInternalVisible)(false);
        }
      });
    }
  }, [visible]);

  const backdropAnimatedStyle = useAnimatedStyle(() => ({
    opacity: progress.value,
  }));

  const sheetAnimatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: interpolate(progress.value, [0, 1], [SCREEN_HEIGHT, 0]) }],
  }));

  return (
    <Modal visible={internalVisible} transparent animationType="none" onRequestClose={onClose}>
      {/* Modal content renders in a separate native surface outside the app's root
          view — gesture-handler's own touch dispatch doesn't reach it without its
          own nested root, which is what causes scroll gestures to misbehave inside
          Modals (most notably on Android). */}
      <GestureHandlerRootView style={{ flex: 1 }}>
        <Animated.View style={[{ flex: 1 }, backdropAnimatedStyle]}>
          <Pressable style={styles.backdrop} onPress={onClose}>
            <Animated.View style={sheetAnimatedStyle}>
              {/* Plain View responder claim (not a Touchable) absorbs the tap so it
                  doesn't fall through to the backdrop's onPress={onClose}, without
                  inserting a competing Touchable ahead of any ScrollView inside
                  children in RN's responder negotiation chain. */}
              <View onStartShouldSetResponder={() => true}>{children}</View>
            </Animated.View>
          </Pressable>
        </Animated.View>
      </GestureHandlerRootView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
});
