import DateTimePicker from '@react-native-community/datetimepicker';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import DownIcon from '@/assets/images/common/down.svg';
import PrevIcon from '@/assets/images/common/prev.svg';
import CaffeineIcon from '@/assets/images/foodDiary/caffeine.svg';
import SodiumIcon from '@/assets/images/foodDiary/sodium.svg';
import SugarIcon from '@/assets/images/foodDiary/sugar.svg';
import { authColors } from '@/components/auth/colors';
import { fonts, nanumSquareRound } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import { ApiError, createFoodLog, createPersonalFoodItem } from '@/lib/api-client';

const UNITS = ['개', 'g', 'ml', '인분'];

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
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmedName = foodName.trim();
  const parsedAmount = Number(amount);
  const isAmountValid = amount.trim() !== '' && !Number.isNaN(parsedAmount) && parsedAmount > 0;
  const isFormValid = trimmedName.length > 0 && isAmountValid;

  const handleSave = () => {
    if (!isFormValid || !user?.user_id || !date || saving) return;

    const caffeine = caffeineMg.trim() === '' ? null : Number(caffeineMg);
    const sugar = sugarG.trim() === '' ? 0 : Number(sugarG);
    const sodium = sodiumMg.trim() === '' ? 0 : Number(sodiumMg);
    const eatenAt = toEatenAt(date, time);

    setSaving(true);
    setError(null);

    createPersonalFoodItem({
      user_id: user.user_id,
      food_name: trimmedName,
      caffeine_mg: caffeine,
      sugar_g: sugar,
      sodium_mg: sodium,
      calories_kcal: 0,
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
          calories_kcal: 0,
          eaten_at: eatenAt,
        }).catch((err) => {
          const message = err instanceof ApiError ? err.message : (err as Error).message;
          throw new Error(`LOG_FAILED: ${message}`);
        })
      )
      .then(() => {
        router.replace('/(tabs)/home/food-diary');
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
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 7 }]}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
          <PrevIcon width={15} height={15} />
        </Pressable>
        <Text style={styles.title}>직접 입력</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.fieldLabel}>음식 이름</Text>
        <TextInput
          style={styles.nameInput}
          value={foodName}
          onChangeText={setFoodName}
          placeholder="예: 아메리카노"
          placeholderTextColor={authColors.gray}
        />
      </View>

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

      <View style={styles.card}>
        <Text style={styles.fieldLabel}>섭취시간</Text>
        <Pressable style={styles.timeInput} onPress={() => setShowTimePicker(true)}>
          <Text style={styles.timeInputText}>{formatTimeLabel(time)}</Text>
          <DownIcon width={10} height={10} style={styles.timeInputChevron} />
        </Pressable>
        {showTimePicker && (
          <DateTimePicker
            value={time}
            mode="time"
            display={Platform.OS === 'ios' ? 'spinner' : 'default'}
            onChange={(_, selected) => {
              setShowTimePicker(Platform.OS === 'ios');
              if (selected) setTime(selected);
            }}
          />
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.fieldLabel}>주요 성분 입력</Text>
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
        <Text style={styles.nutrientHint}>
          정확한 수치를 모르면 비워두세요{'\n'}(정보 없음으로 처리됩니다)
        </Text>
      </View>

      {error && <Text style={styles.errorText}>{error}</Text>}

      <Pressable
        style={[styles.saveButton, (!isFormValid || saving) && styles.saveButtonDisabled]}
        onPress={handleSave}
        disabled={!isFormValid || saving}>
        <Text style={styles.saveButtonText}>{saving ? '저장 중...' : '기록 저장'}</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: authColors.white,
  },
  content: {
    paddingHorizontal: 17,
    paddingBottom: 40,
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
    borderColor: '#F8BFC0',
    borderRadius: 15,
    padding: 19,
    marginTop: 16,
  },
  fieldLabel: {
    fontFamily: fonts.medium,
    fontSize: 14,
    color: '#000000',
  },
  nameInput: {
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 10,
    height: 42,
    paddingHorizontal: 16,
    fontSize: 13,
    color: '#000000',
    marginTop: 10,
  },
  amountRow: {
    marginTop: 10,
    gap: 8,
  },
  amountInput: {
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 7,
    height: 32,
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
    paddingHorizontal: 12,
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
    borderRadius: 7,
    height: 32,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 10,
  },
  timeInputText: {
    fontSize: 12,
    color: '#4A4A4A',
  },
  timeInputChevron: {
    marginLeft: 6,
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
  nutrientHint: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
    marginTop: 12,
  },
  nutrientInput: {
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 7,
    height: 27,
    width: 118,
    paddingHorizontal: 10,
    fontSize: 12,
    color: '#000000',
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
    fontFamily: nanumSquareRound.bold,
    fontSize: 19,
    color: authColors.white,
  },
});
