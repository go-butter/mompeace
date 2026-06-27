import { LinearGradient } from 'expo-linear-gradient';
import { router } from 'expo-router';
import { useState } from 'react';
import {
  ActivityIndicator,
  Image,
  LayoutChangeEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Defs, RadialGradient, Rect, Stop } from 'react-native-svg';

const HEART_ASPECT_RATIO = 696 / 588;

import BarcodeIcon from '@/assets/images/home/barcode.svg';
import FoodIcon from '@/assets/images/home/food.svg';
import CalendarIcon from '@/assets/images/home/calendar.svg';
import NoteIcon from '@/assets/images/home/note.svg';
import RemainCoffeeIcon from '@/assets/images/home/home_remain_coffee.svg';
import { authColors } from '@/components/auth/colors';
import { homeColors } from '@/components/home/colors';
import { fonts, nanumSquareRound } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import { useIntake } from '@/context/intake-context';
import { FoodLogEntry } from '@/lib/api-client';

const WEEKDAY_LABELS = ['일', '월', '화', '수', '목', '금', '토'];

function formatTodayLabel(dateStr: string) {
  const date = new Date(`${dateStr}T00:00:00`);
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  const weekday = WEEKDAY_LABELS[date.getDay()];
  return `${yyyy}.${mm}.${dd} (${weekday})`;
}

function StatusChip({
  label,
  value,
  colors,
}: {
  label: string;
  value: string;
  colors: { label: string; value: string; bg: string };
}) {
  return (
    <View style={[styles.chip, { backgroundColor: colors.bg }]}>
      <Text style={[styles.chipLabel, { color: colors.label }]}>{label}</Text>
      <Text style={[styles.chipValue, { color: colors.value }]}>{value}</Text>
    </View>
  );
}

function ShortcutButton({
  icon,
  title,
  subtitle,
  onPress,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  onPress: () => void;
}) {
  return (
    <Pressable style={styles.shortcutButton} onPress={onPress}>
      <View style={styles.shortcutIconCircle}>{icon}</View>
      <Text style={styles.shortcutTitle}>{title}</Text>
      <Text style={styles.shortcutSubtitle}>{subtitle}</Text>
    </Pressable>
  );
}

function FoodLogRow({ entry }: { entry: FoodLogEntry }) {
  return (
    <View style={styles.foodRow}>
      <Text style={styles.foodTime}>{entry.time}</Text>
      <Text style={styles.foodName}>{entry.food_name}</Text>
      <Text style={styles.foodKcal}>
        {entry.calories_kcal != null ? `${entry.calories_kcal}kcal` : ''}
      </Text>
    </View>
  );
}

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const { intake, foodLog, hasEntries, loading, error } = useIntake();
  const [bannerSize, setBannerSize] = useState({ width: 0, height: 0 });

  const handleBannerLayout = (event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    setBannerSize({ width, height });
  };

  if (loading) {
    return (
      <View style={[styles.centered, { paddingTop: insets.top }]}>
        <ActivityIndicator size="large" color={authColors.pink} />
      </View>
    );
  }

  if (error || !intake) {
    return (
      <View style={[styles.centered, { paddingTop: insets.top }]}>
        <Text style={styles.errorText}>{error || '데이터를 불러오지 못했습니다.'}</Text>
      </View>
    );
  }

  const caffeinePercent = Math.min(intake.progress.caffeine_percent, 100);

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 20 }]}>
      <Image
        source={require('@/assets/images/common/logo_2.png')}
        style={styles.logo}
        resizeMode="contain"
      />

      <View style={styles.banner} onLayout={handleBannerLayout}>
        {bannerSize.width > 0 && bannerSize.height > 0 && (
          <>
            <Svg
              width={bannerSize.width}
              height={bannerSize.height}
              style={[StyleSheet.absoluteFillObject, { zIndex: 0 }]}>
              <Defs>
                <RadialGradient
                  id="bannerGradient"
                  gradientUnits="userSpaceOnUse"
                  cx={bannerSize.width * 0.5}
                  cy={bannerSize.height * 0.5}
                  rx={bannerSize.width * 0.75}
                  ry={bannerSize.height * 0.9}>
                  <Stop offset="0" stopColor="#FFFFFF" stopOpacity="1" />
                  <Stop offset="0.2" stopColor="#FFF8F7" stopOpacity="1" />
                  <Stop offset="0.55" stopColor="#FFEDEB" stopOpacity="1" />
                  <Stop offset="1" stopColor="#FFE0DD" stopOpacity="1" />
                </RadialGradient>
              </Defs>
              <Rect
                x={0}
                y={0}
                width={bannerSize.width}
                height={bannerSize.height}
                fill="url(#bannerGradient)"
              />
            </Svg>
            <Image
              source={require('@/assets/images/home/heart_3d.png')}
              style={[
                styles.bannerIllustration,
                {
                  zIndex: 1,
                  height: bannerSize.height * 0.95,
                  width: bannerSize.height * 0.95 * HEART_ASPECT_RATIO,
                  top: bannerSize.height * 0.025,
                },
              ]}
              resizeMode="contain"
            />
          </>
        )}
        <View style={[styles.bannerTextArea, { zIndex: 2 }]}>
          <Text style={styles.bannerGreeting}>{user?.nickname}님, 오늘도 맘편하게</Text>
          <Text style={styles.bannerWeek}>
            ♥ {intake.pregnancy_week}주 {intake.pregnancy_day}일
          </Text>
          <Text style={styles.bannerDate}>{formatTodayLabel(intake.date)}</Text>
          {intake.days_until_due != null && (
            <View style={styles.ddayPill}>
              <Text style={styles.ddayText}>예정일 D-{intake.days_until_due}</Text>
            </View>
          )}
        </View>
      </View>

      <View style={styles.card}>
        <View style={styles.cardHeaderRow}>
          <Text style={styles.cardTitle}>오늘의 섭취 요약</Text>
          <Text style={styles.cardSubtitle}>기준: 주차별 1일 권장 허용량</Text>
        </View>

        {!hasEntries ? (
          <Text style={styles.emptyMessage}>
            오늘 섭취한 음식이 추가되지 않았습니다!{'\n'}Food Diary 혹은 바코드 스캔을 통해{'\n'}
            음식을 추가해 주세요 :)
          </Text>
        ) : (
          <>
            <View style={styles.intakeRow}>
              <View style={styles.caffeineBox}>
                <Text style={styles.caffeineLabel}>☕ 카페인</Text>
                <Text style={styles.caffeineValueWrapper}>
                  <Text style={styles.caffeineValueNumber}>{intake.intake.total_caffeine}</Text>
                  <Text style={styles.caffeineValueUnit}>
                    {' '}
                    / {intake.limits.caffeine_limit_mg}mg
                  </Text>
                </Text>
                <View style={styles.progressRow}>
                  <View style={styles.progressBarTrack}>
                    <View style={[styles.progressBarFill, { width: `${caffeinePercent}%` }]} />
                  </View>
                  <Text style={styles.caffeinePercent}>{intake.progress.caffeine_percent}%</Text>
                </View>
              </View>
              <View style={styles.remainingBox}>
                <LinearGradient
                  colors={['#FEF6F6', '#FEEBEA']}
                  start={{ x: 0, y: 0 }}
                  end={{ x: 0, y: 1 }}
                  style={StyleSheet.absoluteFillObject}
                />
                <RemainCoffeeIcon
                  width={100}
                  height={100}
                  style={[styles.remainingIcon, { right: -10, top: 16 }]}
                />
                <Text style={styles.remainingLabel}>잔여 허용량</Text>
                <Text style={styles.remainingValueWrapper}>
                  <Text style={styles.remainingValueNumber}>
                    {intake.remaining.remaining_caffeine}
                  </Text>
                  <Text style={styles.remainingValueUnit}>mg</Text>
                </Text>
              </View>
            </View>

            <View style={styles.chipRow}>
              <StatusChip label="당류" value={intake.status_label.sugar} colors={homeColors.sugar} />
              <StatusChip
                label="나트륨"
                value={intake.status_label.sodium}
                colors={homeColors.sodium}
              />
              <StatusChip label="알레르기" value="안전" colors={homeColors.allergy} />
              <StatusChip label="물" value={`${intake.water_cups ?? 0}잔`} colors={homeColors.water} />
            </View>
          </>
        )}
      </View>

      <View style={styles.shortcutCard}>
        <ShortcutButton
          icon={<BarcodeIcon width={24} height={24} />}
          title="바코드 스캔"
          subtitle="식품 안전 확인"
          onPress={() => router.push('/(tabs)/scan')}
        />
        <ShortcutButton
          icon={<FoodIcon width={24} height={24} />}
          title="오늘의 추천"
          subtitle="섭취 가능 음식"
          onPress={() => router.push('/(tabs)/recommend')}
        />
        <ShortcutButton
          icon={<CalendarIcon width={24} height={24} />}
          title="Food Diary"
          subtitle="음식 기록장"
          onPress={() => {}}
        />
        <ShortcutButton
          icon={<NoteIcon width={24} height={24} />}
          title="나의 기록"
          subtitle="스캔 기록 보기"
          onPress={() => {}}
        />
      </View>

      {hasEntries && (
        <View style={styles.card}>
          <View style={styles.cardHeaderRow}>
            <Text style={styles.cardTitle}>오늘 먹은 음식</Text>
            <Text
              style={styles.viewAllText}
              onPress={() => router.push('/(tabs)/home/food-diary-list')}>
              전체 보기 {'>'}
            </Text>
          </View>
          {foodLog.map((entry) => (
            <FoodLogRow key={entry.log_id} entry={entry} />
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#FFF9F8',
  },
  content: {
    paddingHorizontal: 19,
    paddingTop: 20,
    paddingBottom: 32,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FFF9F8',
  },
  errorText: {
    fontFamily: fonts.regular,
    color: authColors.pink,
    fontSize: 14,
    textAlign: 'center',
    paddingHorizontal: 24,
  },
  logo: {
    width: 110,
    height: 29,
    marginBottom: 16,
  },
  banner: {
    position: 'relative',
    borderRadius: 24,
    overflow: 'hidden',
    paddingVertical: 20,
    paddingLeft: 28,
    paddingRight: 20,
    minHeight: 160,
    justifyContent: 'center',
  },
  bannerIllustration: {
    position: 'absolute',
    right: 4,
  },
  bannerTextArea: {
    alignSelf: 'flex-start',
  },
  bannerGreeting: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 12,
    color: authColors.gray,
  },
  bannerWeek: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 22.5,
    color: authColors.brown,
    letterSpacing: -0.2,
    marginTop: 8,
  },
  bannerDate: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 13,
    color: '#4A4A4A',
    marginTop: 4,
  },
  ddayPill: {
    alignSelf: 'flex-start',
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 25,
    minWidth: 96,
    height: 28,
    paddingHorizontal: 14,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 12,
  },
  ddayText: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 13,
    color: authColors.brown,
  },
  card: {
    backgroundColor: authColors.white,
    borderRadius: 24,
    padding: 20,
    marginTop: 20,
    shadowColor: authColors.pink,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.12,
    shadowRadius: 16,
    elevation: 4,
  },
  cardHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  cardTitle: {
    fontFamily: fonts.medium,
    fontSize: 16,
    color: '#000000',
  },
  cardSubtitle: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
  },
  viewAllText: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: authColors.gray,
  },
  emptyMessage: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
    textAlign: 'center',
    marginTop: 36,
    marginBottom: 24,
    lineHeight: 22,
  },
  intakeRow: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 16,
  },
  caffeineBox: {
    flex: 1,
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 10,
    padding: 14,
  },
  caffeineLabel: {
    fontFamily: fonts.medium,
    fontSize: 13,
    color: authColors.brown,
  },
  caffeineValueWrapper: {
    marginTop: 6,
  },
  caffeineValueNumber: {
    fontFamily: fonts.bold,
    fontSize: 22,
    color: authColors.pink,
  },
  caffeineValueUnit: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: authColors.gray,
  },
  progressRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 4,
  },
  progressBarTrack: {
    flex: 1,
    height: 6,
    backgroundColor: authColors.border,
    borderRadius: 3,
    overflow: 'hidden',
  },
  progressBarFill: {
    height: 6,
    backgroundColor: authColors.pink,
    borderRadius: 3,
  },
  caffeinePercent: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
  },
  remainingBox: {
    flex: 1,
    borderWidth: 0.7,
    borderColor: '#ECDEDD',
    borderRadius: 10,
    overflow: 'hidden',
    padding: 14,
  },
  remainingIcon: {
    position: 'absolute',
  },
  remainingLabel: {
    fontFamily: fonts.medium,
    fontSize: 13,
    color: authColors.brown,
  },
  remainingValueWrapper: {
    marginTop: 28,
  },
  remainingValueNumber: {
    fontFamily: fonts.bold,
    fontSize: 22,
    color: authColors.pink,
  },
  remainingValueUnit: {
    fontFamily: fonts.medium,
    fontSize: 20,
    color: authColors.pink,
  },
  chipRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 14,
  },
  chip: {
    flex: 1,
    borderRadius: 12,
    paddingVertical: 10,
    alignItems: 'center',
  },
  chipLabel: {
    fontFamily: fonts.regular,
    fontSize: 11,
  },
  chipValue: {
    fontFamily: fonts.bold,
    fontSize: 13,
    marginTop: 4,
  },
  shortcutCard: {
    flexDirection: 'row',
    backgroundColor: authColors.white,
    borderRadius: 24,
    padding: 16,
    marginTop: 20,
    justifyContent: 'space-between',
    shadowColor: authColors.pink,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.12,
    shadowRadius: 16,
    elevation: 4,
  },
  shortcutButton: {
    alignItems: 'center',
    flex: 1,
  },
  shortcutIconCircle: {
    width: 48,
    height: 48,
    borderRadius: 16,
    backgroundColor: '#FFF0F0',
    alignItems: 'center',
    justifyContent: 'center',
  },
  shortcutTitle: {
    fontFamily: fonts.medium,
    fontSize: 12,
    color: authColors.brown,
    marginTop: 8,
    textAlign: 'center',
  },
  shortcutSubtitle: {
    fontFamily: fonts.regular,
    fontSize: 10,
    color: authColors.gray,
    marginTop: 2,
    textAlign: 'center',
  },
  foodRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: authColors.border,
  },
  foodTime: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
    width: 50,
  },
  foodName: {
    fontFamily: fonts.medium,
    fontSize: 14,
    color: authColors.brown,
    flex: 1,
  },
  foodKcal: {
    fontFamily: fonts.medium,
    fontSize: 13,
    color: authColors.pink,
  },
});
