import { router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Dimensions, Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import Animated, {
  interpolate,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import BarcodeIcon from '@/assets/images/common/tab_barcode.svg';
import CoffeeIcon from '@/assets/images/common/coffee.svg';
import SearchIcon from '@/assets/images/scan/search.svg';
import { authColors } from '@/components/auth/colors';
import { fonts, nanumSquareRound } from '@/constants/fonts';

const SCREEN_HEIGHT = Dimensions.get('window').height;
const ENTER_SPRING_CONFIG = { damping: 20, stiffness: 90, mass: 1 };
const EXIT_SPRING_CONFIG = { damping: 22, stiffness: 60, mass: 1.2 };

export default function AddFoodPopup({
  visible,
  onClose,
  selectedDate,
}: {
  visible: boolean;
  onClose: () => void;
  selectedDate: string;
}) {
  const insets = useSafeAreaInsets();
  const [internalVisible, setInternalVisible] = useState(visible);
  const progress = useSharedValue(0);
  const isClosingRef = useRef(false);
  const barcodeScale = useSharedValue(1);
  const searchScale = useSharedValue(1);
  const coffeeScale = useSharedValue(1);

  useEffect(() => {
    if (visible) {
      isClosingRef.current = false;
      setInternalVisible(true);
      progress.value = withSpring(1, ENTER_SPRING_CONFIG);
    }
  }, [visible]);

  const runDismiss = () => {
    if (isClosingRef.current) return;
    isClosingRef.current = true;
    progress.value = withSpring(0, EXIT_SPRING_CONFIG, (finished) => {
      if (finished) {
        runOnJS(setInternalVisible)(false);
        runOnJS(onClose)();
      }
    });
  };

  const goToBarcodeScan = () => {
    runDismiss();
    router.push('/(tabs)/scan');
  };

  const goToSearch = () => {
    runDismiss();
    router.push({ pathname: '/(tabs)/home/food-entry-search', params: { date: selectedDate } });
  };

  const goToCoffeeCalculator = () => {
    runDismiss();
    router.push({ pathname: '/(tabs)/home/food-entry-coffee', params: { date: selectedDate } });
  };

  const d = new Date();
  const todayLocal = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const isToday = selectedDate === todayLocal;
  const subtitle = isToday
    ? '먹은 음식을 편하게 기록해 보세요 :)'
    : '그날 먹은 음식을 편하게 기록해 보세요 :)';

  const backdropAnimatedStyle = useAnimatedStyle(() => ({
    opacity: progress.value,
  }));

  const sheetAnimatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: interpolate(progress.value, [0, 1], [SCREEN_HEIGHT, 0]) }],
  }));

  const barcodeCardStyle = useAnimatedStyle(() => ({
    transform: [{ scale: barcodeScale.value }],
  }));

  const searchCardStyle = useAnimatedStyle(() => ({
    transform: [{ scale: searchScale.value }],
  }));

  const coffeeCardStyle = useAnimatedStyle(() => ({
    transform: [{ scale: coffeeScale.value }],
  }));

  return (
    <Modal visible={internalVisible} transparent animationType="none" onRequestClose={runDismiss}>
      <Animated.View style={[{ flex: 1 }, backdropAnimatedStyle]}>
        <Pressable style={styles.backdrop} onPress={runDismiss}>
          <Animated.View style={sheetAnimatedStyle}>
            <Pressable
              style={[styles.sheet, { paddingBottom: styles.sheet.paddingBottom + insets.bottom }]}
              onPress={() => {}}>
              <Text style={styles.title}>새 식사 기록하기</Text>
              <Text style={styles.subtitle}>{subtitle}</Text>

              <View style={styles.buttonRow}>
                <Pressable
                  style={styles.optionButton}
                  onPress={goToBarcodeScan}
                  onPressIn={() => {
                    barcodeScale.value = withTiming(0.97, { duration: 90 });
                  }}
                  onPressOut={() => {
                    barcodeScale.value = withTiming(1, { duration: 90 });
                  }}>
                  <Animated.View style={barcodeCardStyle}>
                    <View style={styles.optionIconWrap}>
                      <BarcodeIcon width={31} height={32} color={authColors.pink} />
                    </View>
                    <Text style={styles.optionLabel}>바코드 스캔</Text>
                    <Text style={styles.optionDesc}>마트·편의점 상품{'\n'}빠르게 기록</Text>
                  </Animated.View>
                </Pressable>

                <Pressable
                  style={styles.optionButton}
                  onPress={goToSearch}
                  onPressIn={() => {
                    searchScale.value = withTiming(0.97, { duration: 90 });
                  }}
                  onPressOut={() => {
                    searchScale.value = withTiming(1, { duration: 90 });
                  }}>
                  <Animated.View style={searchCardStyle}>
                    <View style={styles.optionIconWrap}>
                      <SearchIcon width={32} height={32} />
                    </View>
                    <Text style={styles.optionLabel}>음식 검색 및{'\n'}직접 입력</Text>
                    <Text style={styles.optionDesc}>카페 음료·식사 메뉴{'\n'}검색/직접 기록</Text>
                  </Animated.View>
                </Pressable>

                <Pressable
                  style={styles.optionButton}
                  onPress={goToCoffeeCalculator}
                  onPressIn={() => {
                    coffeeScale.value = withTiming(0.97, { duration: 90 });
                  }}
                  onPressOut={() => {
                    coffeeScale.value = withTiming(1, { duration: 90 });
                  }}>
                  <Animated.View style={coffeeCardStyle}>
                    <View style={styles.optionIconWrap}>
                      <CoffeeIcon width={30} height={30} color={authColors.pink} />
                    </View>
                    <Text style={styles.optionLabel}>커피 계산</Text>
                    <Text style={styles.optionDesc}>브랜드 메뉴로{'\n'}카페인 확인</Text>
                  </Animated.View>
                </Pressable>
              </View>

              <Pressable onPress={runDismiss}>
                <Text style={styles.cancelText}>취소하기</Text>
              </Pressable>
            </Pressable>
          </Animated.View>
        </Pressable>
      </Animated.View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: authColors.white,
    borderTopLeftRadius: 30,
    borderTopRightRadius: 30,
    paddingTop: 36,
    paddingHorizontal: 19,
    paddingBottom: 40,
  },
  title: {
    fontFamily: fonts.medium,
    fontSize: 25,
    color: '#000000',
    textAlign: 'left',
  },
  subtitle: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 15,
    color: authColors.gray,
    marginTop: 8,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 16,
  },
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
  cancelText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 15,
    color: authColors.pink,
    textAlign: 'center',
    marginTop: 20,
    textDecorationLine: 'underline',
  },
});
