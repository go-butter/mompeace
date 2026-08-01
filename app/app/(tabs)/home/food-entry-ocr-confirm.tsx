import DateTimePicker from '@react-native-community/datetimepicker';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import Animated, {
  Easing,
  interpolate,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import ChevronDownIcon from '@/assets/images/common/chevron_down_plain.svg';
import CautionIcon from '@/assets/images/scan/caution.svg';
import ClockIcon from '@/assets/images/common/clock.svg';
import PrevIcon from '@/assets/images/common/prev.svg';
import SearchIcon from '@/assets/images/scan/search.svg';
import CaffeineIcon from '@/assets/images/foodDiary/caffeine.svg';
import SodiumIcon from '@/assets/images/foodDiary/sodium.svg';
import SugarIcon from '@/assets/images/foodDiary/sugar.svg';
import { authColors } from '@/components/auth/colors';
import { fonts, nanumSquareRound } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import { ApiError, createFoodLog, OcrScaleMethod } from '@/lib/api-client';

const UNITS = ['개', 'g', 'ml', '인분'];
const EXPAND_SPRING_CONFIG = { damping: 16, stiffness: 100, mass: 1 };
const DRAFT_ROW_HEIGHT = 42;
const TIME_PICKER_HEIGHT = 216;

function sanitizeNonNegativeDecimal(text: string) {
  const digitsAndDot = text.replace(/[^0-9.]/g, '');
  const firstDotIndex = digitsAndDot.indexOf('.');
  if (firstDotIndex === -1) return digitsAndDot;
  return (
    digitsAndDot.slice(0, firstDotIndex + 1) +
    digitsAndDot.slice(firstDotIndex + 1).replace(/\./g, '')
  );
}

function formatTimeLabel(time: Date) {
  const hours = time.getHours();
  const minutes = time.getMinutes();
  const period = hours < 12 ? '오전' : '오후';
  const displayHour = hours % 12 === 0 ? 12 : hours % 12;
  return `${period} ${displayHour}:${String(minutes).padStart(2, '0')}`;
}

function toEatenAt(date: string, time: Date) {
  const hh = String(time.getHours()).padStart(2, '0');
  const min = String(time.getMinutes()).padStart(2, '0');
  const ss = String(time.getSeconds()).padStart(2, '0');
  return `${date} ${hh}:${min}:${ss}`;
}

function scaleTransparencyText(scaleMethod: OcrScaleMethod, scaleFactor: number | null) {
  if (scaleFactor == null) return null;
  if (scaleMethod === 'per_basis_with_total') {
    return `라벨 기준량 대비 총 내용량 비율을 적용해 환산했어요 (×${scaleFactor.toFixed(2)})`;
  }
  if (scaleMethod === 'per_serving_with_count') {
    return `1회 제공량에 총 제공 횟수를 곱해 환산했어요 (×${scaleFactor.toFixed(2)})`;
  }
  return null;
}

type DraftRowProps = {
  row: { id: string; name: string; value: string };
  onRemove: (id: string) => void;
  onUpdate: (id: string, field: 'name' | 'value', text: string) => void;
};

function DraftRow({ row, onRemove, onUpdate }: DraftRowProps) {
  const height = useSharedValue(0);
  const opacity = useSharedValue(0);

  useEffect(() => {
    height.value = withTiming(DRAFT_ROW_HEIGHT, { duration: 400, easing: Easing.out(Easing.cubic) });
    opacity.value = withTiming(1, { duration: 400 });
  }, []);

  const animatedStyle = useAnimatedStyle(() => ({
    height: height.value,
    opacity: opacity.value,
    overflow: 'hidden',
  }));

  const handleRemove = () => {
    height.value = withTiming(0, { duration: 400, easing: Easing.out(Easing.cubic) });
    opacity.value = withTiming(0, { duration: 300 }, (finished) => {
      if (finished) runOnJS(onRemove)(row.id);
    });
  };

  return (
    <Animated.View style={animatedStyle}>
      <View style={styles.extraInputRow}>
        <TextInput
          style={styles.extraNameInput}
          placeholder="성분명"
          placeholderTextColor={authColors.gray}
          value={row.name}
          onChangeText={(text) => onUpdate(row.id, 'name', text)}
        />
        <TextInput
          style={styles.extraValueInput}
          placeholder="수치"
          placeholderTextColor={authColors.gray}
          value={row.value}
          onChangeText={(text) => onUpdate(row.id, 'value', text)}
          returnKeyType="done"
        />
        <Pressable hitSlop={8} onPress={handleRemove} style={styles.draftRemoveButton}>
          <Text style={styles.draftRemoveText}>×</Text>
        </Pressable>
      </View>
    </Animated.View>
  );
}

export default function FoodEntryOcrConfirmScreen() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const params = useLocalSearchParams<{
    date: string;
    product_name?: string;
    sugar_g?: string;
    sodium_mg?: string;
    scale_method?: string;
    scale_factor_applied?: string;
    needs_review?: string;
  }>();

  const needsReview = params.needs_review === 'true';
  const scaleMethod = (params.scale_method ?? 'unknown') as OcrScaleMethod;
  const scaleFactor =
    params.scale_factor_applied && params.scale_factor_applied !== ''
      ? Number(params.scale_factor_applied)
      : null;
  const transparencyText = scaleTransparencyText(scaleMethod, scaleFactor);

  const [foodName, setFoodName] = useState(params.product_name ?? '');
  const [amount, setAmount] = useState('1');
  const [unit, setUnit] = useState(UNITS[0]);
  const [time, setTime] = useState(new Date());
  const [showTimePicker, setShowTimePicker] = useState(false);
  const [caffeineMg, setCaffeineMg] = useState('');
  const [sugarG, setSugarG] = useState(params.sugar_g ?? '');
  const [sodiumMg, setSodiumMg] = useState(params.sodium_mg ?? '');
  const [draftRows, setDraftRows] = useState<{ id: string; name: string; value: string }[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chevronRotation = useSharedValue(0);
  const timePickerHeight = useSharedValue(0);
  const timePickerOpacity = useSharedValue(0);

  const trimmedName = foodName.trim();
  const parsedAmount = Number(amount);
  const isAmountValid = amount.trim() !== '' && !Number.isNaN(parsedAmount) && parsedAmount > 0;
  const isFormValid = trimmedName.length > 0 && isAmountValid;

  const timeChevronAnimatedStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${interpolate(chevronRotation.value, [0, 1], [0, 180])}deg` }],
  }));

  const timePickerAnimatedStyle = useAnimatedStyle(() => ({
    height: timePickerHeight.value,
    opacity: timePickerOpacity.value,
    overflow: 'hidden',
  }));

  const openTimePicker = () => {
    setShowTimePicker(true);
    chevronRotation.value = withSpring(1, EXPAND_SPRING_CONFIG);
    timePickerHeight.value = withTiming(TIME_PICKER_HEIGHT, {
      duration: 400,
      easing: Easing.out(Easing.cubic),
    });
    timePickerOpacity.value = withTiming(1, { duration: 400 });
  };

  const closeTimePicker = () => {
    chevronRotation.value = withSpring(0, EXPAND_SPRING_CONFIG);
    timePickerHeight.value = withTiming(0, {
      duration: 400,
      easing: Easing.out(Easing.cubic),
    });
    timePickerOpacity.value = withTiming(0, { duration: 300 }, (finished) => {
      if (finished) runOnJS(setShowTimePicker)(false);
    });
  };

  const toggleTimePicker = () => {
    if (showTimePicker) {
      closeTimePicker();
    } else {
      openTimePicker();
    }
  };

  const addDraftRow = () => {
    setDraftRows((prev) => [
      ...prev,
      { id: String(Date.now()) + Math.random(), name: '', value: '' },
    ]);
  };

  const updateDraftRow = (id: string, field: 'name' | 'value', text: string) => {
    setDraftRows((prev) => prev.map((r) => (r.id === id ? { ...r, [field]: text } : r)));
  };

  const removeDraftRow = (id: string) => {
    setDraftRows((prev) => prev.filter((r) => r.id !== id));
  };

  const handleSave = () => {
    if (!isFormValid || !user?.user_id || !params.date || saving) return;

    const caffeine = caffeineMg.trim() === '' ? null : Number(caffeineMg);
    const sugar = sugarG.trim() === '' ? null : Number(sugarG);
    const sodium = sodiumMg.trim() === '' ? null : Number(sodiumMg);
    const eatenAt = toEatenAt(params.date, time);

    setSaving(true);
    setError(null);

    createFoodLog({
      user_id: user.user_id,
      food_name: trimmedName,
      input_type: 'ocr',
      amount: Number(amount) || 1,
      unit,
      caffeine_mg: caffeine,
      sugar_g: sugar,
      sodium_mg: sodium,
      calories_kcal: 0,
      needs_review: needsReview,
      eaten_at: eatenAt,
      extra_nutrients: draftRows
        .filter((r) => r.name.trim() && r.value.trim())
        .map((r) => ({ name: r.name.trim(), value: r.value.trim() })),
    })
      .then(() => {
        router.replace('/(tabs)/home/food-diary');
      })
      .catch((err) => {
        const message = err instanceof ApiError ? err.message : (err as Error).message;
        setError(message || '저장에 실패했어요. 다시 시도해주세요.');
      })
      .finally(() => setSaving(false));
  };

  return (
    <KeyboardAvoidingView
      style={styles.keyboardAvoidingView}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={0}>
      <ScrollView
        style={styles.container}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={[
          styles.content,
          { paddingTop: insets.top + 7, paddingBottom: insets.bottom + 40 },
        ]}>
        <View style={styles.headerRow}>
          <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
            <PrevIcon width={15} height={15} />
          </Pressable>
          <Text style={styles.title}>스캔 결과 확인</Text>
        </View>

        {needsReview && (
          <View style={styles.warningBanner}>
            <CautionIcon width={16} height={16} />
            <Text style={styles.warningBannerText}>
              라벨 환산 방식을 정확히 파악하지 못했어요. 당류·나트륨 수치를 직접 확인해
              입력해주세요.
            </Text>
          </View>
        )}

        {/* 상품명 */}
        <View style={styles.card}>
          <Text style={styles.fieldLabel}>상품명</Text>
          <View style={styles.nameInputRow}>
            <SearchIcon width={16} height={16} color={authColors.gray} />
            <TextInput
              style={styles.nameTextInput}
              value={foodName}
              onChangeText={setFoodName}
              placeholder="예: 감자깡"
              placeholderTextColor={authColors.gray}
            />
          </View>
        </View>

        {/* 섭취량 */}
        <View style={styles.card}>
          <Text style={styles.fieldLabel}>섭취량</Text>
          <View style={styles.amountRow}>
            <TextInput
              style={styles.amountInput}
              value={amount}
              onChangeText={setAmount}
              keyboardType="numeric"
            />
            <View style={styles.unitPillRow}>
              {UNITS.map((u) => (
                <Pressable
                  key={u}
                  style={[styles.unitPill, unit === u && styles.unitPillSelected]}
                  onPress={() => setUnit(u)}>
                  <Text style={[styles.unitPillText, unit === u && styles.unitPillTextSelected]}>
                    {u}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
        </View>

        {/* 섭취시간 */}
        <View style={styles.card}>
          <Text style={styles.fieldLabel}>섭취시간</Text>
          <Pressable style={styles.timeInput} onPress={toggleTimePicker}>
            <ClockIcon width={15} height={15} style={styles.timeInputClock} />
            <Text style={styles.timeInputText}>{formatTimeLabel(time)}</Text>
            <Animated.View style={[styles.timeInputChevron, timeChevronAnimatedStyle]}>
              <ChevronDownIcon width={12} height={8} />
            </Animated.View>
          </Pressable>
          {showTimePicker && (
            <Animated.View
              style={[
                Platform.OS === 'ios' ? styles.timePickerContainer : undefined,
                timePickerAnimatedStyle,
              ]}>
              <DateTimePicker
                value={time}
                mode="time"
                display={Platform.OS === 'ios' ? 'spinner' : 'default'}
                themeVariant="light"
                onChange={(_, selected) => {
                  const nextVisible = Platform.OS === 'ios';
                  if (!nextVisible) closeTimePicker();
                  if (selected) setTime(selected);
                }}
              />
            </Animated.View>
          )}
        </View>

        {/* 주요 성분 */}
        <View style={styles.card}>
          <View style={styles.nutrientHeaderRow}>
            <View>
              <Text style={styles.fieldLabel}>주요 성분</Text>
            </View>
            <Pressable style={styles.addNutrientPill} onPress={addDraftRow}>
              <Text style={styles.addNutrientPillText}>+ 성분 추가</Text>
            </Pressable>
          </View>

          <View style={styles.nutrientInputRow}>
            <View style={styles.nutrientLabelGroup}>
              <CaffeineIcon width={17} height={17} />
              <Text style={styles.nutrientLabel}>카페인(mg)</Text>
            </View>
            <TextInput
              style={styles.nutrientInput}
              value={caffeineMg}
              onChangeText={(text) => setCaffeineMg(sanitizeNonNegativeDecimal(text))}
              placeholder="예: 65"
              placeholderTextColor={authColors.gray}
              keyboardType="decimal-pad"
            />
          </View>

          {transparencyText && (
            <Text style={styles.transparencyText}>※ {transparencyText}</Text>
          )}

          <View style={styles.nutrientInputRow}>
            <View style={styles.nutrientLabelGroup}>
              <SugarIcon width={17} height={17} />
              <Text style={styles.nutrientLabel}>당류(g)</Text>
            </View>
            <TextInput
              style={styles.nutrientInput}
              value={sugarG}
              onChangeText={(text) => setSugarG(sanitizeNonNegativeDecimal(text))}
              placeholder="예: 8"
              placeholderTextColor={authColors.gray}
              keyboardType="decimal-pad"
            />
          </View>
          <View style={styles.nutrientInputRow}>
            <View style={styles.nutrientLabelGroup}>
              <SodiumIcon width={18} height={18} />
              <Text style={styles.nutrientLabel}>나트륨(mg)</Text>
            </View>
            <TextInput
              style={styles.nutrientInput}
              value={sodiumMg}
              onChangeText={(text) => setSodiumMg(sanitizeNonNegativeDecimal(text))}
              placeholder="예: 420"
              placeholderTextColor={authColors.gray}
              keyboardType="decimal-pad"
            />
          </View>

          <View>
            {draftRows.map((row) => (
              <DraftRow
                key={row.id}
                row={row}
                onRemove={removeDraftRow}
                onUpdate={updateDraftRow}
              />
            ))}
          </View>
        </View>

        {error && <Text style={styles.errorText}>{error}</Text>}

        <Pressable
          style={[styles.saveButton, (!isFormValid || saving) && styles.saveButtonDisabled]}
          onPress={handleSave}
          disabled={!isFormValid || saving}>
          <Text style={styles.saveButtonText}>{saving ? '저장 중...' : '기록 저장'}</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  keyboardAvoidingView: {
    flex: 1,
  },
  container: {
    flex: 1,
    backgroundColor: authColors.white,
  },
  content: {
    paddingHorizontal: 17,
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
  warningBanner: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    backgroundColor: '#FFF0F0',
    borderWidth: 1,
    borderColor: authColors.pink,
    borderRadius: 12,
    padding: 14,
    marginTop: 16,
  },
  warningBannerText: {
    flex: 1,
    fontFamily: fonts.regular,
    fontSize: 11.5,
    color: authColors.pink,
    lineHeight: 17,
  },
  card: {
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: '#FFEDEE',
    borderRadius: 15,
    padding: 19,
    marginTop: 16,
    shadowColor: '#F47E8A',
    shadowOpacity: 0.05,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 0 },
    elevation: 3,
  },
  fieldLabel: {
    fontFamily: fonts.medium,
    fontSize: 14,
    color: '#000000',
  },
  nameInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    paddingHorizontal: 12,
    height: 42,
    marginTop: 10,
  },
  nameTextInput: {
    flex: 1,
    fontSize: 13,
    color: '#000000',
  },
  amountRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 10,
    gap: 8,
  },
  amountInput: {
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    height: 32,
    width: 170,
    paddingHorizontal: 12,
    fontSize: 12,
    color: '#000000',
  },
  unitPillRow: {
    flexDirection: 'row',
    gap: 6,
  },
  unitPill: {
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 100,
    paddingHorizontal: 5,
    paddingVertical: 5,
  },
  unitPillSelected: {
    borderColor: authColors.pink,
    backgroundColor: '#FFF5F3',
  },
  unitPillText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 11,
    color: authColors.gray,
  },
  unitPillTextSelected: {
    color: authColors.pink,
  },
  timeInput: {
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    height: 32,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 10,
  },
  timeInputClock: {
    marginRight: 6,
  },
  timeInputText: {
    flex: 1,
    fontSize: 12,
    color: '#4A4A4A',
  },
  timeInputChevron: {
    marginLeft: 4,
  },
  timePickerContainer: {
    height: 216,
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    marginTop: 10,
    overflow: 'hidden',
  },
  nutrientHeaderRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
  },
  addNutrientPill: {
    borderWidth: 1,
    borderColor: authColors.pink,
    borderRadius: 100,
    paddingHorizontal: 12,
    paddingVertical: 5,
  },
  addNutrientPillText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 11,
    color: authColors.pink,
  },
  transparencyText: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
    marginTop: 8,
  },
  nutrientInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 12,
  },
  nutrientLabelGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  nutrientLabel: {
    fontSize: 12,
    color: '#000000',
  },
  nutrientInput: {
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    height: 27,
    width: 118,
    paddingHorizontal: 10,
    fontSize: 12,
    color: '#000000',
  },
  extraInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 12,
    width: '100%',
    paddingRight: 4,
  },
  extraNameInput: {
    flex: 4.5,
    minWidth: 0,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    height: 30,
    paddingHorizontal: 8,
    fontSize: 12,
    color: '#000000',
  },
  extraValueInput: {
    flex: 4,
    minWidth: 0,
    marginRight: 8,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    height: 30,
    paddingHorizontal: 8,
    fontSize: 12,
    color: '#000000',
  },
  draftRemoveButton: {
    flex: 0,
    flexShrink: 0,
    width: 20,
    height: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  draftRemoveText: {
    fontSize: 18,
    color: authColors.gray,
    lineHeight: 20,
  },
  errorText: {
    fontFamily: fonts.regular,
    color: authColors.pink,
    fontSize: 12,
    textAlign: 'center',
    marginTop: 16,
  },
  saveButton: {
    marginTop: 20,
    backgroundColor: authColors.pink,
    borderRadius: 100,
    height: 51,
    alignItems: 'center',
    justifyContent: 'center',
  },
  saveButtonDisabled: {
    opacity: 0.6,
  },
  saveButtonText: {
    fontFamily: fonts.semiBold,
    fontSize: 19,
    color: authColors.white,
  },
});
