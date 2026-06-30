import { LinearGradient } from 'expo-linear-gradient';
import { router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Alert, FlatList, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { interpolate, useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';

import PrevIcon from '@/assets/images/common/prev.svg';
import DownIcon from '@/assets/images/common/down.svg';
import RemainCoffeeIcon from '@/assets/images/home/home_remain_coffee.svg';
import { authColors } from '@/components/auth/colors';
import { homeColors } from '@/components/home/colors';
import AddFoodPopup from '@/components/home/AddFoodPopup';
import Calendar from '@/components/home/Calendar';
import { fonts } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import { useFoodDiary } from '@/context/food-diary-context';
import { ApiError, deleteFoodLog, FoodLogEntry } from '@/lib/api-client';

const EXPAND_SPRING_CONFIG = { damping: 16, stiffness: 100, mass: 1 };

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

function FoodLogRow({ entry, onDelete }: { entry: FoodLogEntry; onDelete: (entry: FoodLogEntry) => void }) {
  return (
    <View style={styles.foodRow}>
      <Text style={styles.foodTime}>{entry.time}</Text>
      <Text style={styles.foodName}>{entry.food_name}</Text>
      <Text style={styles.foodKcal}>
        {entry.calories_kcal != null ? `${entry.calories_kcal}kcal` : ''}
      </Text>
      <Pressable onPress={() => onDelete(entry)} hitSlop={8}>
        <Text style={styles.deleteText}>삭제</Text>
      </Pressable>
    </View>
  );
}

export default function FoodDiaryScreen() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const {
    year,
    month,
    selectedDate,
    setSelectedDate,
    changeMonth,
    statusByDate,
    intake,
    foodLog,
    loading,
    error,
    isToday,
    refreshDay,
  } = useFoodDiary();

  const [popupVisible, setPopupVisible] = useState(false);

  const handleDelete = (entry: FoodLogEntry) => {
    Alert.alert('기록 삭제', `'${entry.food_name}' 기록을 삭제할까요?`, [
      { text: '취소', style: 'cancel' },
      {
        text: '삭제',
        style: 'destructive',
        onPress: () => {
          if (!user?.user_id) return;
          deleteFoodLog(entry.log_id, user.user_id)
            .then(() => refreshDay())
            .catch((err) => {
              const message = err instanceof ApiError ? err.message : (err as Error).message;
              Alert.alert('삭제 실패', message);
            });
        },
      },
    ]);
  };

  const [summaryExpanded, setSummaryExpanded] = useState(false);
  const expandProgress = useSharedValue(0);
  const summaryContentHeight = useSharedValue(0);

  const toggleSummaryExpanded = () => {
    const next = !summaryExpanded;
    setSummaryExpanded(next);
    expandProgress.value = withSpring(next ? 1 : 0, EXPAND_SPRING_CONFIG);
  };

  const summaryContentAnimatedStyle = useAnimatedStyle(() => ({
    height: interpolate(expandProgress.value, [0, 1], [0, summaryContentHeight.value]),
    opacity: expandProgress.value,
    transform: [{ scaleY: interpolate(expandProgress.value, [0, 1], [0.85, 1]) }],
  }));

  const chevronAnimatedStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${interpolate(expandProgress.value, [0, 1], [0, 180])}deg` }],
  }));

  const caffeinePercent = intake ? Math.min(intake.progress.caffeine_percent, 100) : 0;
  const hasEntries = foodLog.length > 0;

  return (
    <View style={[styles.container, { paddingTop: insets.top + 7 }]}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
          <PrevIcon width={15} height={15} />
        </Pressable>
        <Text style={styles.title}>Food Diary</Text>
      </View>

      <View style={styles.fixedSection}>
        <Calendar
          year={year}
          month={month}
          selectedDate={selectedDate}
          statusByDate={statusByDate}
          onSelectDate={setSelectedDate}
          onChangeMonth={changeMonth}
        />

        <View style={styles.card}>
          <Pressable style={styles.cardHeaderRow} onPress={toggleSummaryExpanded} hitSlop={8}>
            <View style={styles.cardHeaderTitleGroup}>
              <Text style={styles.cardTitle}>섭취 요약</Text>
              <Text style={styles.cardSubtitle}>기준: 주차별 1일 권장 허용량</Text>
            </View>
            <Animated.View style={chevronAnimatedStyle}>
              <DownIcon width={19} height={19} />
            </Animated.View>
          </Pressable>

          <Animated.View style={[styles.summaryContentOuter, summaryContentAnimatedStyle]}>
            <View
              onLayout={(event) => {
                summaryContentHeight.value = event.nativeEvent.layout.height;
              }}>
              {loading ? (
                <ActivityIndicator size="small" color={authColors.pink} style={{ marginVertical: 24 }} />
              ) : error || !intake ? (
                <Text style={styles.errorText}>{error || '데이터를 불러오지 못했습니다.'}</Text>
              ) : !hasEntries ? (
                <Text style={styles.emptyMessage}>
                  {isToday
                    ? '오늘 섭취한 음식이 추가되지 않았습니다!\nFood Diary 혹은 바코드 스캔을 통해\n음식을 추가해 주세요 :)'
                    : '이 날에는 기록된 음식이 없어요.'}
                </Text>
              ) : (
                <>
                  <View style={styles.intakeRow}>
                    <View style={styles.caffeineBox}>
                      <Text style={styles.caffeineLabel}>☕ 카페인</Text>
                      <Text style={styles.caffeineValueWrapper}>
                        <Text style={styles.caffeineValueNumber}>{intake.intake.total_caffeine}</Text>
                        <Text style={styles.caffeineValueUnit}> / {intake.limits.caffeine_limit_mg}mg</Text>
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
                    <StatusChip
                      label="당류"
                      value={intake.status_label.sugar}
                      colors={homeColors.sugar}
                    />
                    <StatusChip
                      label="나트륨"
                      value={intake.status_label.sodium}
                      colors={homeColors.sodium}
                    />
                    <StatusChip label="알레르기" value="안전" colors={homeColors.allergy} />
                    <StatusChip
                      label="물"
                      value={`${intake.water_cups ?? 0}잔`}
                      colors={homeColors.water}
                    />
                  </View>
                </>
              )}
            </View>
          </Animated.View>

          <Pressable onPress={() => router.push('/(tabs)/home/premium-report')}>
            <Text style={styles.premiumLink}>프리미엄 리포트 보기 {'>'}</Text>
          </Pressable>
        </View>
      </View>

      <FlatList
        style={styles.scrollSection}
        contentContainerStyle={styles.listContent}
        data={foodLog}
        keyExtractor={(item) => String(item.log_id)}
        ListHeaderComponent={
          <View style={styles.listHeaderRow}>
            <Text style={styles.cardTitle}>식사 기록</Text>
            <Pressable onPress={() => setPopupVisible(true)}>
              <Text style={styles.addButtonText}>+ 음식 추가하기</Text>
            </Pressable>
          </View>
        }
        renderItem={({ item }) => <FoodLogRow entry={item} onDelete={handleDelete} />}
        ListEmptyComponent={
          !loading ? <Text style={styles.emptyListText}>기록된 음식이 없어요.</Text> : null
        }
      />

      <AddFoodPopup
        visible={popupVisible}
        onClose={() => setPopupVisible(false)}
        selectedDate={selectedDate}
      />
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
  fixedSection: {
    paddingHorizontal: 19,
    gap: 20,
    marginTop: 16,
  },
  card: {
    backgroundColor: authColors.white,
    borderRadius: 25,
    padding: 20,
    shadowColor: '#FFEEF0',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 12,
    elevation: 4,
  },
  cardHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  cardHeaderTitleGroup: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 6,
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
  summaryContentOuter: {
    overflow: 'hidden',
  },
  errorText: {
    fontFamily: fonts.regular,
    color: authColors.pink,
    fontSize: 13,
    textAlign: 'center',
    marginVertical: 24,
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
  premiumLink: {
    fontFamily: fonts.medium,
    fontSize: 12,
    color: authColors.pink,
    textAlign: 'right',
    marginTop: 16,
  },
  scrollSection: {
    flex: 1,
    marginTop: 12,
    paddingHorizontal: 19,
  },
  listContent: {
    paddingBottom: 32,
  },
  listHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  addButtonText: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: authColors.pink,
  },
  emptyListText: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
    textAlign: 'center',
    paddingVertical: 24,
  },
  foodRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: authColors.border,
    backgroundColor: authColors.white,
    paddingHorizontal: 16,
    borderRadius: 10,
    marginBottom: 4,
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
  deleteText: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: authColors.gray,
    marginLeft: 12,
  },
});
