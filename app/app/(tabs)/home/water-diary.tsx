import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Dimensions,
  Keyboard,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, {
  interpolate,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
} from 'react-native-reanimated';

import PrevIcon from '@/assets/images/common/prev.svg';
import XIcon from '@/assets/images/common/x.svg';
import { authColors } from '@/components/auth/colors';
import { waterColors } from '@/components/water/colors';
import WaterWaveCircle from '@/components/water/WaterWaveCircle';
import WaterWeeklyMiniCircles from '@/components/water/WaterWeeklyMiniCircles';
import { fonts, nanumSquareRound } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import { useIntake } from '@/context/intake-context';
import {
  ApiError,
  createWaterLog,
  deleteWaterLog,
  getWaterWeek,
  WaterLogEntry,
  WaterWeekResponse,
} from '@/lib/api-client';

const SCREEN_HEIGHT = Dimensions.get('window').height;
const ENTER_SPRING_CONFIG = { damping: 20, stiffness: 90, mass: 1 };
const EXIT_SPRING_CONFIG = { damping: 22, stiffness: 60, mass: 1.2 };
const PRESET_AMOUNTS = [100, 200, 250, 500];

function WaterLogRow({
  entry,
  onDelete,
}: {
  entry: WaterLogEntry;
  onDelete: (entry: WaterLogEntry) => void;
}) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowTime}>{entry.time}</Text>
      <Text style={styles.rowAmount}>{Math.round(entry.amount_ml)}ml</Text>
      <Pressable onPress={() => onDelete(entry)} hitSlop={8} style={styles.deleteButton}>
        <XIcon width={19} height={19} color={authColors.pink} />
      </Pressable>
    </View>
  );
}

function CustomAmountSheet({
  visible,
  onClose,
  onSubmit,
}: {
  visible: boolean;
  onClose: () => void;
  onSubmit: (amountMl: number) => void;
}) {
  const insets = useSafeAreaInsets();
  const [internalVisible, setInternalVisible] = useState(visible);
  const [customValue, setCustomValue] = useState('');
  const progress = useSharedValue(0);
  const isClosingRef = useRef(false);

  useEffect(() => {
    if (visible) {
      isClosingRef.current = false;
      setInternalVisible(true);
      setCustomValue('');
      progress.value = withSpring(1, ENTER_SPRING_CONFIG);
    }
  }, [visible, progress]);

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

  const handlePreset = (amount: number) => {
    Keyboard.dismiss();
    runDismiss();
    onSubmit(amount);
  };

  const handleCustomSubmit = () => {
    Keyboard.dismiss();
    const amount = parseFloat(customValue);
    if (!amount || amount <= 0) return;
    runDismiss();
    onSubmit(amount);
  };

  const backdropAnimatedStyle = useAnimatedStyle(() => ({ opacity: progress.value }));
  const sheetAnimatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: interpolate(progress.value, [0, 1], [SCREEN_HEIGHT, 0]) }],
  }));

  return (
    <Modal visible={internalVisible} transparent animationType="none" onRequestClose={runDismiss}>
      <Animated.View style={[{ flex: 1 }, backdropAnimatedStyle]}>
        <KeyboardAvoidingView
          style={styles.keyboardAvoidingView}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          keyboardVerticalOffset={0}>
          <Pressable style={styles.backdrop} onPress={runDismiss}>
            <Animated.View style={sheetAnimatedStyle}>
              <Pressable
                style={[styles.sheet, { paddingBottom: styles.sheet.paddingBottom + insets.bottom }]}
                onPress={() => {}}>
                <Text style={styles.sheetTitle}>수분 섭취량 추가</Text>
                <Text style={styles.sheetSubtitle}>원하는 양을 선택하거나 직접 입력해 주세요</Text>

                <View style={styles.presetRow}>
                  {PRESET_AMOUNTS.map((amount) => (
                    <Pressable key={amount} style={styles.presetChip} onPress={() => handlePreset(amount)}>
                      <Text style={styles.presetChipText}>{amount}ml</Text>
                    </Pressable>
                  ))}
                </View>

                <View style={styles.customInputRow}>
                  <TextInput
                    style={styles.customInput}
                    placeholder="직접 입력 (ml)"
                    placeholderTextColor={authColors.gray}
                    keyboardType="numeric"
                    value={customValue}
                    onChangeText={setCustomValue}
                  />
                  <Pressable style={styles.customSubmitButton} onPress={handleCustomSubmit}>
                    <Text style={styles.customSubmitText}>추가</Text>
                  </Pressable>
                </View>

                <Pressable onPress={runDismiss}>
                  <Text style={styles.cancelText}>취소하기</Text>
                </Pressable>
              </Pressable>
            </Animated.View>
          </Pressable>
        </KeyboardAvoidingView>
      </Animated.View>
    </Modal>
  );
}

export default function WaterDiaryScreen() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const { water, refresh: refreshIntake } = useIntake();
  const [weekData, setWeekData] = useState<WaterWeekResponse | null>(null);
  const [weekLoading, setWeekLoading] = useState(true);
  const [weekError, setWeekError] = useState<string | null>(null);
  const [sheetVisible, setSheetVisible] = useState(false);

  const fetchWeek = useCallback(() => {
    if (!user?.user_id) return;
    setWeekLoading(true);
    setWeekError(null);
    getWaterWeek(user.user_id)
      .then(setWeekData)
      .catch((err) => setWeekError(err instanceof ApiError ? err.message : (err as Error).message))
      .finally(() => setWeekLoading(false));
  }, [user?.user_id]);

  useFocusEffect(
    useCallback(() => {
      refreshIntake();
      fetchWeek();
    }, [refreshIntake, fetchWeek])
  );

  const addWater = (amountMl: number) => {
    if (!user?.user_id) return;
    createWaterLog({ user_id: user.user_id, amount_ml: amountMl })
      .then(() => {
        refreshIntake();
        fetchWeek();
      })
      .catch((err) => {
        const message = err instanceof ApiError ? err.message : (err as Error).message;
        Alert.alert('기록 실패', message);
      });
  };

  const handleDeleteEntry = (entry: WaterLogEntry) => {
    Alert.alert('기록 삭제', `${Math.round(entry.amount_ml)}ml 기록을 삭제할까요?`, [
      { text: '취소', style: 'cancel' },
      {
        text: '삭제',
        style: 'destructive',
        onPress: () => {
          if (!user?.user_id) return;
          deleteWaterLog(entry.log_id, user.user_id)
            .then(() => {
              refreshIntake();
              fetchWeek();
            })
            .catch((err) => {
              const message = err instanceof ApiError ? err.message : (err as Error).message;
              Alert.alert('삭제 실패', message);
            });
        },
      },
    ]);
  };

  const percent = water?.percent ?? 0;
  const totalMl = water?.total_ml ?? 0;
  const targetMl = water?.target_ml ?? 0;
  const motivationText =
    percent >= 100
      ? '오늘 목표를 달성했어요! 정말 잘하고 있어요 :)'
      : `오늘 목표의 ${Math.round(percent)}%를 채웠어요`;

  return (
    <View style={styles.container}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={[
          styles.content,
          { paddingTop: insets.top + 7, paddingBottom: insets.bottom + 32 },
        ]}>
        <View style={styles.headerRow}>
          <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
            <PrevIcon width={15} height={15} />
          </Pressable>
          <Text style={styles.title}>수분 다이어리</Text>
        </View>

        <View style={styles.waveCard}>
          <WaterWaveCircle percent={percent} currentMl={totalMl} targetMl={targetMl} size={200} />
          <Text style={styles.motivationText}>{motivationText}</Text>
        </View>

        <View style={styles.actionRow}>
          <Pressable style={styles.primaryButton} onPress={() => addWater(250)}>
            <Text style={styles.primaryButtonText}>+ 1잔 (250ml)</Text>
          </Pressable>
          <Pressable style={styles.customButton} onPress={() => setSheetVisible(true)} hitSlop={8}>
            <Text style={styles.customButtonText}>직접 입력</Text>
          </Pressable>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>주간 수분 섭취</Text>
          {weekLoading ? (
            <ActivityIndicator size="small" color={waterColors.chip.value} style={styles.weekLoading} />
          ) : weekError ? (
            <Text style={styles.errorText}>{weekError}</Text>
          ) : weekData ? (
            <View style={styles.weekCirclesWrapper}>
              <WaterWeeklyMiniCircles days={weekData.days} targetMl={weekData.target_ml} />
            </View>
          ) : null}
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>오늘의 기록</Text>
          {!water || water.logs.length === 0 ? (
            <Text style={styles.emptyText}>오늘 기록된 수분 섭취가 없어요.</Text>
          ) : (
            water.logs.map((entry) => (
              <WaterLogRow key={entry.log_id} entry={entry} onDelete={handleDeleteEntry} />
            ))
          )}
        </View>
      </ScrollView>

      <CustomAmountSheet
        visible={sheetVisible}
        onClose={() => setSheetVisible(false)}
        onSubmit={addWater}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#FFF9F8',
  },
  scroll: {
    flex: 1,
  },
  content: {
    paddingHorizontal: 19,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  prevButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#FFF0F0',
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontFamily: fonts.semiBold,
    fontSize: 20,
    color: authColors.brown,
  },
  waveCard: {
    marginTop: 20,
    backgroundColor: authColors.white,
    borderRadius: 25,
    paddingVertical: 24,
    alignItems: 'center',
    shadowColor: '#FFEEF0',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 12,
    elevation: 4,
  },
  motivationText: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 14,
    color: authColors.brown,
    marginTop: 16,
    textAlign: 'center',
  },
  actionRow: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 16,
  },
  primaryButton: {
    flex: 1,
    backgroundColor: waterColors.primaryButtonBg,
    borderRadius: 16,
    paddingVertical: 16,
    alignItems: 'center',
  },
  primaryButtonText: {
    fontFamily: fonts.semiBold,
    fontSize: 15,
    color: authColors.brown,
  },
  customButton: {
    backgroundColor: authColors.white,
    borderRadius: 16,
    paddingHorizontal: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  customButtonText: {
    fontFamily: fonts.medium,
    fontSize: 13,
    color: authColors.brown,
  },
  card: {
    backgroundColor: authColors.white,
    borderRadius: 25,
    padding: 20,
    marginTop: 20,
    shadowColor: '#FFEEF0',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 12,
    elevation: 4,
  },
  cardTitle: {
    fontFamily: fonts.medium,
    fontSize: 16,
    color: '#000000',
  },
  weekLoading: {
    marginVertical: 24,
  },
  weekCirclesWrapper: {
    marginTop: 16,
  },
  errorText: {
    fontFamily: fonts.regular,
    color: authColors.pink,
    fontSize: 13,
    textAlign: 'center',
    marginVertical: 24,
  },
  emptyText: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
    textAlign: 'center',
    paddingVertical: 24,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: authColors.border,
  },
  rowTime: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
    width: 50,
  },
  rowAmount: {
    fontFamily: fonts.medium,
    fontSize: 14,
    color: authColors.brown,
    flex: 1,
  },
  deleteButton: {
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  keyboardAvoidingView: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
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
  sheetTitle: {
    fontFamily: fonts.medium,
    fontSize: 22,
    color: '#000000',
  },
  sheetSubtitle: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 14,
    color: authColors.gray,
    marginTop: 8,
  },
  presetRow: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 20,
  },
  presetChip: {
    flex: 1,
    backgroundColor: waterColors.chip.bg,
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: 'center',
  },
  presetChipText: {
    fontFamily: fonts.medium,
    fontSize: 14,
    color: waterColors.chip.value,
  },
  customInputRow: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 14,
  },
  customInput: {
    flex: 1,
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 14,
    paddingHorizontal: 16,
    paddingVertical: 12,
    fontFamily: fonts.regular,
    fontSize: 14,
    color: '#000000',
  },
  customSubmitButton: {
    backgroundColor: authColors.pink,
    borderRadius: 14,
    paddingHorizontal: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  customSubmitText: {
    fontFamily: fonts.semiBold,
    fontSize: 14,
    color: authColors.white,
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
