import { Ionicons } from '@expo/vector-icons';
import DateTimePicker from '@react-native-community/datetimepicker';
import { router } from 'expo-router';
import type { CSSProperties } from 'react';
import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import BabyIcon from '@/assets/images/onboarding/baby.svg';
import CalIcon from '@/assets/images/onboarding/cal.svg';
import InformationIcon from '@/assets/images/onboarding/information.svg';
import { authColors } from '@/components/auth/colors';
import { GradientBackground } from '@/components/auth/gradient-background';
import { fonts } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
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

const WEB_DATE_INPUT_CLASS = 'mompeace-web-date-input';
const WEB_DATE_INPUT_STYLE_TAG_ID = 'mompeace-web-date-input-style';

function ensureWebDateInputStyleInjected() {
  if (typeof document === 'undefined' || document.getElementById(WEB_DATE_INPUT_STYLE_TAG_ID)) {
    return;
  }
  const style = document.createElement('style');
  style.id = WEB_DATE_INPUT_STYLE_TAG_ID;
  style.textContent = `
    .${WEB_DATE_INPUT_CLASS}::-webkit-calendar-picker-indicator {
      opacity: 0;
      pointer-events: none;
    }
  `;
  document.head.appendChild(style);
}

export default function PregnancyInputScreen() {
  const { user, login } = useAuth();
  const [week, setWeek] = useState('21');
  const [day, setDay] = useState('3');
  const [dueDate, setDueDate] = useState(new Date(2026, 9, 26));
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const webDateInputRef = useRef<HTMLInputElement | null>(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    if (Platform.OS === 'web') {
      ensureWebDateInputStyleInjected();
    }
  }, []);

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

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

  const handleNext = async () => {
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
      });
      login({
        ...user,
        pregnancy_week: response.pregnancy_week,
        pregnancy_day: response.pregnancy_day,
        pregnancy_entered_at: response.pregnancy_entered_at,
        due_date: response.due_date,
      });
      if (!isMountedRef.current) return;
      router.push('/(tabs)/home');
    } catch (err) {
      if (!isMountedRef.current) return;
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError((err as Error).message);
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  };

  return (
    <View style={styles.container}>
      <GradientBackground />

      <ScrollView contentContainerStyle={styles.content}>
        <Image
          source={require('@/assets/images/common/logo_nottext.png')}
          style={styles.logo}
          resizeMode="contain"
        />

        <Text style={styles.title}>
          <Text style={{ color: authColors.pink }}>기본 정보</Text>
          <Text style={{ color: authColors.brown }}>를{'\n'}입력해 주세요</Text>
        </Text>
        <Text style={styles.subtitle}>
          정확한 정보를 입력할수록{'\n'}더 맘편한 추천을 받을 수 있어요
        </Text>

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
          <Text style={styles.weekHint}>정확한 날짜를 모르신다면 1일로 입력해 주세요</Text>

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
                className={WEB_DATE_INPUT_CLASS}
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
                <Ionicons name="calendar-outline" size={20} color={authColors.pink} />
              </Pressable>
            </View>
          ) : (
            <>
              <Pressable style={styles.dateField} onPress={() => setShowDatePicker(true)}>
                <Text style={styles.dateInput}>{formatDate(dueDate)}</Text>
                <Ionicons name="calendar-outline" size={20} color={authColors.pink} />
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
              임신 주차 또는 출산예정일 중 하나만 입력해도 자동으로 계산해줘요! 수정도 가능해요 :)
            </Text>
          </View>
        </View>
      </ScrollView>

      <View style={styles.footer}>
        {error && <Text style={styles.errorText}>{error}</Text>}
        <Pressable
          style={[styles.nextButton, loading && styles.buttonDisabled]}
          onPress={handleNext}
          disabled={loading}>
          <View style={styles.buttonContent}>
            {loading && <ActivityIndicator size="small" color={authColors.white} />}
            <Text style={styles.nextButtonText}>{loading ? '저장 중...' : '다음'}</Text>
          </View>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    paddingHorizontal: 24,
    paddingTop: 60,
    paddingBottom: 24,
  },
  logo: {
    width: 100,
    height: 68,
    opacity: 0.85,
  },
  title: {
    fontSize: 29,
    fontFamily: fonts.bold,
    marginTop: 20,
    lineHeight: 36,
  },
  subtitle: {
    fontSize: 15,
    fontFamily: fonts.regular,
    color: authColors.gray,
    marginTop: 12,
    lineHeight: 22,
  },
  card: {
    backgroundColor: authColors.white,
    borderRadius: 24,
    padding: 20,
    marginTop: 28,
    shadowColor: authColors.pink,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.25,
    shadowRadius: 20,
    elevation: 8,
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
  weekHint: {
    fontSize: 12,
    fontFamily: fonts.regular,
    color: authColors.gray,
    marginTop: 8,
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
  footer: {
    paddingHorizontal: 24,
    paddingBottom: 32,
  },
  nextButton: {
    backgroundColor: authColors.pink,
    borderRadius: 999,
    paddingVertical: 16,
    alignItems: 'center',
  },
  nextButtonText: {
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
