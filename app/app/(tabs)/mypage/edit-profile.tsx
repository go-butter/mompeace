import DateTimePicker from '@react-native-community/datetimepicker';
import { router } from 'expo-router';
import type { CSSProperties } from 'react';
import { useRef, useState } from 'react';
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import PrevIcon from '@/assets/images/common/prev.svg';
import AgeIcon from '@/assets/images/mypage/mypage_edit_age.svg';
import BabyIcon from '@/assets/images/mypage/mypage_edit_baby.svg';
import CalIcon from '@/assets/images/mypage/mypage_edit_calendar.svg';
import CalButtonIcon from '@/assets/images/mypage/mypage_edit_cal_button.svg';
import InformationIcon from '@/assets/images/mypage/mypage_edit_information.svg';
import { authColors } from '@/components/auth/colors';
import { fonts } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import { useIntake } from '@/context/intake-context';
import { ApiError, updatePregnancyInfo } from '@/lib/api-client';

function formatDate(date: Date) {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  return `${yyyy}.${mm}.${dd}.`;
}

function toInputDateValue(date: Date) {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

const LMP_TOTAL_DAYS = 280;

function addDays(date: Date, days: number) {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

// 임신 주차/일 → 출산 예정일 (280일 LMP 공식 기준 데이터 입력 편의 계산)
function dueDateFromWeekDay(week: number, day: number) {
  const lmp = addDays(new Date(), -(week * 7 + day));
  return addDays(lmp, LMP_TOTAL_DAYS);
}

// 출산 예정일 → 임신 주차/일 (280일 LMP 공식 기준 데이터 입력 편의 계산)
function weekDayFromDueDate(dueDate: Date) {
  const today = new Date();
  const msPerDay = 1000 * 60 * 60 * 24;
  const daysRemaining = Math.round((dueDate.getTime() - today.getTime()) / msPerDay);
  const elapsed = LMP_TOTAL_DAYS - daysRemaining;
  const week = Math.floor(elapsed / 7);
  const day = elapsed % 7;
  return { week, day };
}

const webDateInputStyle: CSSProperties = {
  flex: 1,
  border: 'none',
  outline: 'none',
  background: 'transparent',
  fontSize: 15,
  fontFamily: fonts.regular,
  color: authColors.brown,
};

function parseStoredDueDate(dueDate: string | null | undefined) {
  if (!dueDate) return new Date();
  const parsed = new Date(`${dueDate}T00:00:00`);
  return isNaN(parsed.getTime()) ? new Date() : parsed;
}

export default function EditProfileScreen() {
  const insets = useSafeAreaInsets();
  const { user, login } = useAuth();
  const { refresh } = useIntake();
  const [week, setWeek] = useState(String(user?.pregnancy_week ?? ''));
  const [day, setDay] = useState(String(user?.pregnancy_day ?? ''));
  const [dueDate, setDueDate] = useState(() => parseStoredDueDate(user?.due_date));
  const [ageBracket, setAgeBracket] = useState<'19-29' | '30-49'>(
    user?.age_bracket === '30-49' ? '30-49' : '19-29'
  );
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const webDateInputRef = useRef<HTMLInputElement | null>(null);

  const openWebDatePicker = () => {
    const el = webDateInputRef.current;
    if (!el) return;
    if (typeof (el as any).showPicker === 'function') {
      (el as any).showPicker();
    } else {
      el.focus();
      el.click();
    }
  };

  const handleSave = async () => {
    if (!user?.user_id) {
      setError('사용자 정보를 찾을 수 없습니다. 다시 로그인해 주세요.');
      return;
    }

    setError(null);
    setLoading(true);
    try {
      const response = await updatePregnancyInfo(user.user_id, {
        pregnancy_week: Number(week),
        pregnancy_day: Number(day),
        due_date: toInputDateValue(dueDate),
        age_bracket: ageBracket,
      });
      login({
        ...user,
        pregnancy_week: response.pregnancy_week,
        pregnancy_day: response.pregnancy_day,
        pregnancy_entered_at: response.pregnancy_entered_at,
        due_date: response.due_date,
        age_bracket: response.age_bracket,
      });
      await refresh();
      router.back();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError((err as Error).message);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 7 }]}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
          <PrevIcon width={15} height={15} />
        </Pressable>
        <Text style={styles.title}>정보 수정</Text>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.card}>
          <View style={styles.row}>
            <View style={styles.iconCircle}>
              <BabyIcon width={24} height={24} />
            </View>
            <Text style={styles.rowTitle}>임신 주차</Text>
          </View>
          <View style={styles.weekInputs}>
            <View style={styles.weekField}>
              <TextInput
                style={styles.numberInput}
                value={week}
                onChangeText={(text) => {
                  const filtered = text.replace(/[^0-9]/g, '');
                  if (filtered !== '' && Number(filtered) > 42) {
                    return;
                  }
                  setWeek(filtered);
                  if (filtered !== '') {
                    setDueDate(dueDateFromWeekDay(Number(filtered), Number(day) || 0));
                  }
                }}
                keyboardType="number-pad"
                maxLength={2}
              />
              <Text style={styles.weekLabel}>주차</Text>
            </View>
            <View style={styles.weekField}>
              <TextInput
                style={styles.numberInput}
                value={day}
                onChangeText={(text) => {
                  const filtered = text.replace(/[^0-9]/g, '');
                  if (filtered !== '' && Number(filtered) > 6) {
                    return;
                  }
                  setDay(filtered);
                  if (week !== '') {
                    setDueDate(dueDateFromWeekDay(Number(week), Number(filtered) || 0));
                  }
                }}
                keyboardType="number-pad"
                maxLength={1}
              />
              <Text style={styles.weekLabel}>일</Text>
            </View>
          </View>

          <View style={styles.divider} />

          <View style={styles.row}>
            <View style={styles.iconCircle}>
              <CalIcon width={24} height={24} />
            </View>
            <Text style={styles.rowTitle}>출산 예정일</Text>
          </View>
          {Platform.OS === 'web' ? (
            <View style={styles.dateField}>
              <input
                ref={webDateInputRef}
                type="date"
                value={toInputDateValue(dueDate)}
                onChange={(e) => {
                  const parsed = new Date(e.target.value);
                  if (!isNaN(parsed.getTime())) {
                    setDueDate(parsed);
                    const computed = weekDayFromDueDate(parsed);
                    setWeek(String(computed.week));
                    setDay(String(computed.day));
                  }
                }}
                style={webDateInputStyle}
              />
              <Pressable onPress={openWebDatePicker} hitSlop={8}>
                <CalButtonIcon width={20} height={20} />
              </Pressable>
            </View>
          ) : (
            <>
              <Pressable style={styles.dateField} onPress={() => setShowDatePicker(true)}>
                <Text style={styles.dateInput}>{formatDate(dueDate)}</Text>
                <CalButtonIcon width={20} height={20} />
              </Pressable>
              {showDatePicker && (
                <DateTimePicker
                  value={dueDate}
                  mode="date"
                  display="default"
                  onChange={(_event, selectedDate) => {
                    setShowDatePicker(false);
                    if (selectedDate) {
                      setDueDate(selectedDate);
                      const computed = weekDayFromDueDate(selectedDate);
                      setWeek(String(computed.week));
                      setDay(String(computed.day));
                    }
                  }}
                />
              )}
            </>
          )}

          <View style={styles.banner}>
            <InformationIcon width={18} height={18} />
            <Text style={styles.bannerText}>
              정확한 정보일수록 더 맘편한 추천을 받을 수 있어요
            </Text>
          </View>
        </View>

        <View style={[styles.card, styles.secondCard]}>
          <View style={styles.row}>
            <View style={styles.iconCircle}>
              <AgeIcon width={24} height={24} />
            </View>
            <Text style={styles.rowTitle}>나이대</Text>
          </View>
          <View style={styles.ageBracketRow}>
            {(['19-29', '30-49'] as const).map((bracket) => (
              <Pressable
                key={bracket}
                style={[
                  styles.ageBracketOption,
                  ageBracket === bracket && styles.ageBracketOptionSelected,
                ]}
                onPress={() => setAgeBracket(bracket)}>
                <Text
                  style={[
                    styles.ageBracketOptionText,
                    ageBracket === bracket && styles.ageBracketOptionTextSelected,
                  ]}>
                  {bracket}세
                </Text>
              </Pressable>
            ))}
          </View>
        </View>
      </ScrollView>

      <View style={styles.footer}>
        {error && <Text style={styles.errorText}>{error}</Text>}
        <Pressable
          style={[styles.saveButton, loading && styles.buttonDisabled]}
          onPress={handleSave}
          disabled={loading}>
          <View style={styles.buttonContent}>
            {loading && <ActivityIndicator size="small" color={authColors.white} />}
            <Text style={styles.saveButtonText}>{loading ? '저장 중...' : '기록 저장'}</Text>
          </View>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#FEFAF9',
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 19,
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
  content: {
    paddingHorizontal: 24,
    paddingTop: 20,
    paddingBottom: 24,
  },
  card: {
    backgroundColor: authColors.white,
    borderRadius: 24,
    padding: 20,
    borderWidth: 1,
    borderColor: authColors.border,
  },
  secondCard: {
    marginTop: 16,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  iconCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#FFF0F0',
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowTitle: {
    fontSize: 16,
    fontFamily: fonts.medium,
    color: authColors.brown,
  },
  weekInputs: {
    flexDirection: 'row',
    gap: 16,
    marginTop: 16,
  },
  weekField: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  numberInput: {
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 10,
    fontSize: 15,
    fontFamily: fonts.regular,
    width: 64,
    textAlign: 'center',
  },
  weekLabel: {
    fontSize: 14,
    fontFamily: fonts.regular,
    color: authColors.gray,
  },
  divider: {
    height: 1,
    backgroundColor: authColors.border,
    marginVertical: 20,
  },
  dateField: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 10,
    marginTop: 16,
  },
  dateInput: {
    fontSize: 15,
    fontFamily: fonts.regular,
    flex: 1,
  },
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#FFF5F3',
    borderRadius: 12,
    padding: 12,
    marginTop: 20,
  },
  bannerText: {
    fontSize: 12,
    fontFamily: fonts.regular,
    color: authColors.gray,
    flex: 1,
  },
  ageBracketRow: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 16,
  },
  ageBracketOption: {
    flex: 1,
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: 'center',
  },
  ageBracketOptionSelected: {
    borderColor: authColors.pink,
    backgroundColor: '#FFF0F0',
  },
  ageBracketOptionText: {
    fontSize: 15,
    fontFamily: fonts.regular,
    color: authColors.gray,
  },
  ageBracketOptionTextSelected: {
    fontFamily: fonts.medium,
    color: authColors.pink,
  },
  footer: {
    paddingHorizontal: 24,
    paddingBottom: 32,
  },
  saveButton: {
    backgroundColor: authColors.pink,
    borderRadius: 999,
    paddingVertical: 16,
    alignItems: 'center',
  },
  saveButtonText: {
    color: authColors.white,
    fontSize: 17,
    fontFamily: fonts.bold,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  errorText: {
    color: authColors.pink,
    fontSize: 13,
    fontFamily: fonts.regular,
    textAlign: 'center',
    marginBottom: 12,
  },
});
