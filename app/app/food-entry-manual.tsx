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
  Keyboard,
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
import InformationIcon from '@/assets/images/onboarding/information.svg';
import ClockIcon from '@/assets/images/common/clock.svg';
import PrevIcon from '@/assets/images/common/prev.svg';
import SearchIcon from '@/assets/images/scan/search.svg';
import CaloriesIcon from '@/assets/images/foodDiary/calories.svg';
import CaffeineIcon from '@/assets/images/foodDiary/caffeine.svg';
import SodiumIcon from '@/assets/images/foodDiary/sodium.svg';
import SugarIcon from '@/assets/images/foodDiary/sugar.svg';
import CarbohydrateIcon from '@/assets/images/foodDiary/carbohydrate.svg';
import FatIcon from '@/assets/images/foodDiary/fat.svg';
import IronIcon from '@/assets/images/foodDiary/iron.svg';
import ProteinIcon from '@/assets/images/foodDiary/protein.svg';
import { authColors } from '@/components/auth/colors';
import AmountUnitPicker, { UNITS } from '@/components/food-diary/AmountUnitPicker';
import { fonts, nanumSquareRound } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import { ApiError, createFoodLog, createPersonalFoodItem } from '@/lib/api-client';

const EXPAND_SPRING_CONFIG = { damping: 16, stiffness: 100, mass: 1 };

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

// input height 30 + marginTop 12
const DRAFT_ROW_HEIGHT = 42;
const TIME_PICKER_HEIGHT = 216;

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

export default function FoodEntryManualScreen() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const { date, name } = useLocalSearchParams<{ date: string; name?: string }>();

  const [foodName, setFoodName] = useState(name ?? '');
  const [amount, setAmount] = useState('1');
  const [unit, setUnit] = useState(UNITS[0]);
  const [time, setTime] = useState(new Date());
  const [showTimePicker, setShowTimePicker] = useState(false);
  const [caffeineMg, setCaffeineMg] = useState('');
  const [sugarG, setSugarG] = useState('');
  const [sodiumMg, setSodiumMg] = useState('');
  const [caloriesKcal, setCaloriesKcal] = useState('');
  const [carbohydrateG, setCarbohydrateG] = useState('');
  const [fatG, setFatG] = useState('');
  const [ironMg, setIronMg] = useState('');
  const [proteinG, setProteinG] = useState('');
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
    setDraftRows((prev) =>
      prev.map((r) => (r.id === id ? { ...r, [field]: text } : r))
    );
  };

  const removeDraftRow = (id: string) => {
    setDraftRows((prev) => prev.filter((r) => r.id !== id));
  };

  const handleSave = () => {
    Keyboard.dismiss();
    if (!isFormValid || !user?.user_id || !date || saving) return;

    const caffeine = caffeineMg.trim() === '' ? null : Number(caffeineMg);
    const sugar = sugarG.trim() === '' ? 0 : Number(sugarG);
    const sodium = sodiumMg.trim() === '' ? 0 : Number(sodiumMg);
    const calories = caloriesKcal.trim() === '' ? null : Number(caloriesKcal);
    const carbohydrate = carbohydrateG.trim() === '' ? null : Number(carbohydrateG);
    const fat = fatG.trim() === '' ? null : Number(fatG);
    const iron = ironMg.trim() === '' ? null : Number(ironMg);
    const protein = proteinG.trim() === '' ? null : Number(proteinG);
    const eatenAt = toEatenAt(date, time);

    setSaving(true);
    setError(null);

    createPersonalFoodItem({
      user_id: user.user_id,
      food_name: trimmedName,
      caffeine_mg: caffeine,
      sugar_g: sugar,
      sodium_mg: sodium,
      // UserFoodItemCreate.calories_kcal은 이번 변경 범위 밖이라(별도 과제) 여전히
      // null을 받지 않는다 — food_log 저장(calories, 아래)과 달리 여기서만 0으로 폴백한다.
      calories_kcal: calories ?? 0,
      carbohydrate_g: carbohydrate,
      protein_g: protein,
      fat_g: fat,
      saturated_fat_g: null,
      trans_fat_g: null,
      cholesterol_mg: null,
      iron_mg: iron,
    })
      .catch((err) => {
        const message = err instanceof ApiError ? err.message : (err as Error).message;
        throw new Error(`SAVE_ITEM_FAILED: ${message}`);
      })
      .then(() =>
        createFoodLog({
          user_id: user.user_id,
          food_name: trimmedName,
          input_type: 'manual',
          amount: Number(amount) || 1,
          unit,
          caffeine_mg: caffeine,
          sugar_g: sugar,
          sodium_mg: sodium,
          calories_kcal: calories,
          carbohydrate_g: carbohydrate,
          fat_g: fat,
          iron_mg: iron,
          protein_g: protein,
          eaten_at: eatenAt,
          extra_nutrients: draftRows
            .filter((r) => r.name.trim() && r.value.trim())
            .map((r) => ({ name: r.name.trim(), value: r.value.trim() })),
        }).catch((err) => {
          const message = err instanceof ApiError ? err.message : (err as Error).message;
          throw new Error(`LOG_FAILED: ${message}`);
        })
      )
      .then(() => {
        router.dismissTo('/(tabs)/food-diary');
      })
      .catch((err: Error) => {
        if (err.message.startsWith('LOG_FAILED')) {
          setError(
            '음식 정보는 저장됐지만 기록 추가에 실패했어요. 다시 시도해주세요.'
          );
        } else {
          setError(
            err.message.replace('SAVE_ITEM_FAILED: ', '') || '저장에 실패했어요. 다시 시도해주세요.'
          );
        }
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
        <Text style={styles.title}>직접 입력</Text>
      </View>

      {/* 음식명 */}
      <View style={styles.card}>
        <View style={styles.fieldLabelRow}>
          <View style={styles.stepBadge}>
            <Text style={styles.stepBadgeText}>1</Text>
          </View>
          <Text style={styles.fieldLabel}>음식명</Text>
        </View>
        <View style={styles.nameInputRow}>
          <SearchIcon width={16} height={16} color={authColors.gray} />
          <TextInput
            style={styles.nameTextInput}
            value={foodName}
            onChangeText={setFoodName}
            placeholder="예: 아메리카노"
            placeholderTextColor={authColors.gray}
          />
        </View>
      </View>

      {/* 섭취단위 */}
      <View style={styles.card}>
        <View style={styles.fieldLabelRow}>
          <View style={styles.stepBadge}>
            <Text style={styles.stepBadgeText}>2</Text>
          </View>
          <Text style={styles.fieldLabel}>섭취단위</Text>
        </View>
        <AmountUnitPicker amount={amount} unit={unit} onChangeAmount={setAmount} onChangeUnit={setUnit} />
      </View>

      {/* 섭취시간 */}
      <View style={styles.card}>
        <View style={styles.fieldLabelRow}>
          <View style={styles.stepBadge}>
            <Text style={styles.stepBadgeText}>3</Text>
          </View>
          <Text style={styles.fieldLabel}>섭취시간</Text>
        </View>
        <Pressable style={styles.timeInput} onPress={toggleTimePicker}>
          <ClockIcon width={15} height={15} style={styles.timeInputClock} />
          <Text style={styles.timeInputText}>{formatTimeLabel(time)}</Text>
          <Animated.View style={[styles.timeInputChevron, timeChevronAnimatedStyle]}>
            <ChevronDownIcon width={12} height={8} color="#848484" />
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
          <View style={styles.fieldLabelRow}>
            <View style={styles.stepBadge}>
              <Text style={styles.stepBadgeText}>4</Text>
            </View>
            <Text style={styles.fieldLabel}>주요 성분</Text>
          </View>
          <Pressable style={styles.addNutrientPill} onPress={addDraftRow}>
            <Text style={styles.addNutrientPillText}>+ 성분 추가</Text>
          </Pressable>
        </View>

        <Text style={styles.nutrientHintText}>
          ※ {(amount.trim() || '1')}{unit} 기준으로 영양성분을 작성해주세요
        </Text>

        <View style={styles.nutrientGrid}>
          <View style={styles.nutrientCell}>
            <View style={styles.nutrientLabelGroup}>
              <CaffeineIcon width={17} height={17} color="#F47E8A" />
              <Text style={styles.nutrientLabel} numberOfLines={1}>카페인(mg)</Text>
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
          <View style={styles.nutrientCell}>
            <View style={styles.nutrientLabelGroup}>
              <SugarIcon width={17} height={17} color="#F47E8A" />
              <Text style={styles.nutrientLabel} numberOfLines={1}>당류(g)</Text>
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
          <View style={styles.nutrientCell}>
            <View style={styles.nutrientLabelGroup}>
              <SodiumIcon width={18} height={18} color="#F47E8A" />
              <Text style={styles.nutrientLabel} numberOfLines={1}>나트륨(mg)</Text>
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
          <View style={styles.nutrientCell}>
            <View style={styles.nutrientLabelGroup}>
              <CaloriesIcon width={17} height={17} color="#F47E8A" />
              <Text style={styles.nutrientLabel} numberOfLines={1}>칼로리(kcal)</Text>
            </View>
            <TextInput
              style={styles.nutrientInput}
              value={caloriesKcal}
              onChangeText={(text) => setCaloriesKcal(sanitizeNonNegativeDecimal(text))}
              placeholder="예: 250"
              placeholderTextColor={authColors.gray}
              keyboardType="decimal-pad"
            />
          </View>
          <View style={styles.nutrientCell}>
            <View style={styles.nutrientLabelGroup}>
              <CarbohydrateIcon width={17} height={17} color="#F47E8A" />
              <Text style={styles.nutrientLabel} numberOfLines={1}>탄수화물(g)</Text>
            </View>
            <TextInput
              style={styles.nutrientInput}
              value={carbohydrateG}
              onChangeText={(text) => setCarbohydrateG(sanitizeNonNegativeDecimal(text))}
              placeholder="예: 30"
              placeholderTextColor={authColors.gray}
              keyboardType="decimal-pad"
            />
          </View>
          <View style={styles.nutrientCell}>
            <View style={styles.nutrientLabelGroup}>
              <FatIcon width={17} height={17} color="#F47E8A" />
              <Text style={styles.nutrientLabel} numberOfLines={1}>지방(g)</Text>
            </View>
            <TextInput
              style={styles.nutrientInput}
              value={fatG}
              onChangeText={(text) => setFatG(sanitizeNonNegativeDecimal(text))}
              placeholder="예: 10"
              placeholderTextColor={authColors.gray}
              keyboardType="decimal-pad"
            />
          </View>
          <View style={styles.nutrientCell}>
            <View style={styles.nutrientLabelGroup}>
              <IronIcon width={17} height={17} color="#F47E8A" />
              <Text style={styles.nutrientLabel} numberOfLines={1}>철분(mg)</Text>
            </View>
            <TextInput
              style={styles.nutrientInput}
              value={ironMg}
              onChangeText={(text) => setIronMg(sanitizeNonNegativeDecimal(text))}
              placeholder="예: 2"
              placeholderTextColor={authColors.gray}
              keyboardType="decimal-pad"
            />
          </View>
          <View style={styles.nutrientCell}>
            <View style={styles.nutrientLabelGroup}>
              <ProteinIcon width={17} height={17} color="#F47E8A" />
              <Text style={styles.nutrientLabel} numberOfLines={1}>단백질(g)</Text>
            </View>
            <TextInput
              style={styles.nutrientInput}
              value={proteinG}
              onChangeText={(text) => setProteinG(sanitizeNonNegativeDecimal(text))}
              placeholder="예: 5"
              placeholderTextColor={authColors.gray}
              keyboardType="decimal-pad"
            />
          </View>
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

        <View style={styles.infoBanner}>
          <InformationIcon width={16} height={16} color={authColors.gray} opacity={0.5} />
          <Text style={styles.infoBannerText}>
            정확한 수치를 모르면 비워두세요! 정보 없음으로 처리됩니다 :)
          </Text>
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
    backgroundColor: authColors.white,
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
  fieldLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  stepBadge: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: authColors.pink,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 8,
  },
  stepBadgeText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 12,
    color: authColors.white,
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
  nutrientHintText: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
    marginTop: 8,
  },
  nutrientGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    rowGap: 12,
    marginTop: 12,
  },
  nutrientCell: {
    width: '48%',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  nutrientLabelGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    width: 88,
  },
  nutrientLabel: {
    fontSize: 12,
    color: '#000000',
    flexShrink: 1,
  },
  nutrientInput: {
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 6,
    height: 27,
    flex: 1,
    paddingHorizontal: 8,
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
  infoBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#FFF5F3',
    borderRadius: 12,
    padding: 12,
    marginTop: 12,
  },
  infoBannerText: {
    fontSize: 11,
    fontFamily: fonts.regular,
    color: authColors.gray,
    flex: 1,
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
