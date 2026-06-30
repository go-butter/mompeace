import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { router, useFocusEffect } from 'expo-router';

import PrevIcon from '@/assets/images/common/prev.svg';
import { authColors } from '@/components/auth/colors';
import { fonts, nanumSquareRound } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import {
  ApiError,
  getIntakeToday,
  getRecommendations,
  IntakeTodayResponse,
  RecommendationItem,
  RecommendationResponse,
} from '@/lib/api-client';

type NutrientFilter = 'all' | 'caffeine' | 'sugar' | 'sodium';

const NUTRIENT_CHIPS: { key: NutrientFilter; label: string }[] = [
  { key: 'caffeine', label: '카페인' },
  { key: 'sugar', label: '당류' },
  { key: 'sodium', label: '나트륨' },
];

const NUTRIENT_KEY_MAP = {
  caffeine: 'caffeine_mg',
  sugar: 'sugar_g',
  sodium: 'sodium_mg',
} as const;

const DESSERT_CATEGORIES = new Set(['빵 및 과자류', '유제품류 및 빙과류']);

const DISPLAY_LIMIT = 10;

function filterAndSortPossibleByNutrient(
  items: RecommendationItem[],
  filter: NutrientFilter
): RecommendationItem[] {
  if (filter === 'all') return items;
  const key = NUTRIENT_KEY_MAP[filter];
  const withValue = items.filter((item) => item.nutrients[key] != null);

  if (filter !== 'sugar') {
    return withValue.sort((a, b) => (a.nutrients[key] as number) - (b.nutrients[key] as number));
  }

  const dessertTier = withValue.filter((item) => item.category != null && DESSERT_CATEGORIES.has(item.category));
  const otherTier = withValue.filter((item) => !(item.category != null && DESSERT_CATEGORIES.has(item.category)));
  const bySugarAsc = (a: RecommendationItem, b: RecommendationItem) =>
    (a.nutrients.sugar_g as number) - (b.nutrients.sugar_g as number);
  return [...dessertTier.sort(bySugarAsc), ...otherTier.sort(bySugarAsc)];
}

function NutrientChip({
  label,
  selected,
  onPress,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      style={[styles.chip, selected && styles.chipSelected]}
      onPress={onPress}>
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Text>
    </Pressable>
  );
}

function PossibleCard({ item }: { item: RecommendationItem }) {
  const showReason = !(item.status === 'possible' && item.reason_nutrient === null);
  return (
    <View style={styles.possibleCard}>
      <View style={styles.possibleCardHeader}>
        <Text style={styles.possibleCardName}>{item.food_name}</Text>
        <View style={styles.possibleBadge}>
          <Text style={styles.possibleBadgeText}>{item.label}</Text>
        </View>
      </View>
      {showReason && <Text style={styles.possibleCardReason}>{item.reason}</Text>}
      <Text style={styles.cardNutrients}>
        카페인 {item.nutrients.caffeine_mg ?? '-'}mg · 당류 {item.nutrients.sugar_g ?? '-'}g · 나트륨{' '}
        {item.nutrients.sodium_mg ?? '-'}mg
      </Text>
    </View>
  );
}

function MutedCard({ item }: { item: RecommendationItem }) {
  return (
    <View style={styles.mutedCard}>
      <View style={styles.mutedCardHeader}>
        <Text style={styles.mutedCardName}>{item.food_name}</Text>
        <View style={styles.mutedBadge}>
          <Text style={styles.mutedBadgeText}>{item.label}</Text>
        </View>
      </View>
      <Text style={styles.mutedCardReason}>{item.reason}</Text>
      {item.alternative && (
        <View style={styles.alternativeBox}>
          <Text style={styles.alternativeLabel}>대신 이건 어때요?</Text>
          <Text style={styles.alternativeName}>{item.alternative.food_name}</Text>
        </View>
      )}
    </View>
  );
}

export default function RecommendScreen() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();

  const [selectedNutrient, setSelectedNutrient] = useState<NutrientFilter>('all');

  const [intake, setIntake] = useState<IntakeTodayResponse | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendationResponse | null>(null);

  const [loadingIntake, setLoadingIntake] = useState(true);
  const [loadingRecommendations, setLoadingRecommendations] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loading = loadingIntake || loadingRecommendations;

  const fetchIntake = useCallback(() => {
    if (!user?.user_id) return;
    setLoadingIntake(true);
    getIntakeToday(user.user_id)
      .then(setIntake)
      .catch(() => {})
      .finally(() => setLoadingIntake(false));
  }, [user?.user_id]);

  const fetchRecommendations = useCallback(() => {
    if (!user?.user_id) return;
    setLoadingRecommendations(true);
    setError(null);
    getRecommendations({ user_id: user.user_id, limit: 50 })
      .then(setRecommendations)
      .catch((err) => setError(err instanceof ApiError ? err.message : (err as Error).message))
      .finally(() => setLoadingRecommendations(false));
  }, [user?.user_id]);

  useFocusEffect(
    useCallback(() => {
      fetchIntake();
      fetchRecommendations();
    }, [fetchIntake, fetchRecommendations])
  );

  const allItems = recommendations?.recommendations ?? [];
  const allPossibleItems = allItems.filter((item) => item.status === 'possible');
  const possibleItems = filterAndSortPossibleByNutrient(allPossibleItems, selectedNutrient).slice(
    0,
    DISPLAY_LIMIT
  );
  const mutedItems = allItems.filter((item) => item.status !== 'possible').slice(0, DISPLAY_LIMIT);

  const emptyMessage =
    possibleItems.length === 0 && selectedNutrient !== 'all' && allPossibleItems.length > 0
      ? '이 성분 정보가 있는 음식이 지금 없어요.'
      : '지금 바로 먹을 수 있는 음식이 없어요.';

  return (
    <View style={[styles.container, { paddingTop: insets.top + 7 }]}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
          <PrevIcon width={15} height={15} />
        </Pressable>
        <View>
          <Text style={styles.title}>오늘의 추천</Text>
          <Text style={styles.subtitle}>오늘 남은 허용량 안에서 먹어도 되는 음식이에요 :)</Text>
        </View>
      </View>

      <View style={styles.remainingCard}>
        <LinearGradient
          colors={['#FEF6F6', '#FEEBEA']}
          start={{ x: 0, y: 0 }}
          end={{ x: 0, y: 1 }}
          style={StyleSheet.absoluteFillObject}
        />
        {loadingIntake || !intake ? (
          <ActivityIndicator size="small" color={authColors.pink} style={{ marginVertical: 8 }} />
        ) : (
          <View style={styles.remainingRow}>
            <View style={styles.remainingItem}>
              <Text style={styles.remainingLabel}>카페인</Text>
              <Text style={styles.remainingValue}>{intake.remaining.remaining_caffeine}mg</Text>
            </View>
            <View style={styles.remainingItem}>
              <Text style={styles.remainingLabel}>당류</Text>
              <Text style={styles.remainingValue}>{intake.remaining.remaining_sugar}g</Text>
            </View>
            <View style={styles.remainingItem}>
              <Text style={styles.remainingLabel}>나트륨</Text>
              <Text style={styles.remainingValue}>{intake.remaining.remaining_sodium}mg</Text>
            </View>
          </View>
        )}
        <Text style={styles.remainingFootnote}>오늘 남은 허용량 기준</Text>
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.chipRow}
        contentContainerStyle={styles.chipRowContent}>
        <View style={styles.chipRowInner}>
          {NUTRIENT_CHIPS.map(({ key, label }) => (
            <NutrientChip
              key={key}
              label={label}
              selected={selectedNutrient === key}
              onPress={() => setSelectedNutrient(key)}
            />
          ))}
        </View>
      </ScrollView>

      <ScrollView style={styles.resultsScroll} contentContainerStyle={styles.resultsContent}>
        {loading ? (
          <ActivityIndicator size="small" color={authColors.pink} style={{ marginTop: 32 }} />
        ) : error ? (
          <Text style={styles.errorText}>{error}</Text>
        ) : (
          <>
            {possibleItems.length === 0 && (
              <Text style={styles.emptyMessage}>{emptyMessage}</Text>
            )}
            {possibleItems.map((item) => (
              <PossibleCard key={item.food_id} item={item} />
            ))}
            {mutedItems.length > 0 && (
              <>
                <Text style={styles.sectionLabel}>주의가 필요한 음식</Text>
                {mutedItems.map((item) => (
                  <MutedCard key={item.food_id} item={item} />
                ))}
              </>
            )}
          </>
        )}
      </ScrollView>
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
  subtitle: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
    marginTop: 2,
  },
  remainingCard: {
    marginHorizontal: 19,
    marginTop: 16,
    borderRadius: 16,
    borderWidth: 0.7,
    borderColor: authColors.border,
    overflow: 'hidden',
    padding: 16,
  },
  remainingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  remainingItem: {
    alignItems: 'center',
  },
  remainingLabel: {
    fontFamily: fonts.medium,
    fontSize: 12,
    color: authColors.brown,
  },
  remainingValue: {
    fontFamily: fonts.bold,
    fontSize: 17,
    color: authColors.pink,
    marginTop: 4,
  },
  remainingFootnote: {
    fontFamily: fonts.regular,
    fontSize: 10,
    color: authColors.gray,
    textAlign: 'center',
    marginTop: 10,
  },
  chipRow: {
    marginTop: 16,
    flexGrow: 0,
  },
  chipRowContent: {
    paddingHorizontal: 19,
  },
  chipRowInner: {
    flexDirection: 'row',
    gap: 8,
  },
  chip: {
    alignSelf: 'flex-start',
    backgroundColor: authColors.white,
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 100,
    paddingHorizontal: 14,
    paddingVertical: 7,
  },
  chipSelected: {
    backgroundColor: authColors.pink,
    borderColor: authColors.pink,
  },
  chipText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 11,
    color: authColors.brown,
  },
  chipTextSelected: {
    color: authColors.white,
  },
  resultsScroll: {
    flex: 1,
    marginTop: 16,
    paddingHorizontal: 19,
  },
  resultsContent: {
    paddingBottom: 32,
    gap: 10,
  },
  errorText: {
    fontFamily: fonts.regular,
    color: authColors.pink,
    fontSize: 13,
    textAlign: 'center',
    marginTop: 24,
  },
  emptyMessage: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
    textAlign: 'center',
    marginTop: 12,
    marginBottom: 4,
    lineHeight: 20,
  },
  possibleCard: {
    backgroundColor: authColors.white,
    borderRadius: 16,
    padding: 16,
    shadowColor: '#FFEEF0',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 12,
    elevation: 3,
  },
  possibleCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  possibleCardName: {
    fontFamily: fonts.semiBold,
    fontSize: 15,
    color: authColors.brown,
    flex: 1,
  },
  possibleBadge: {
    backgroundColor: '#FFF5F3',
    borderRadius: 100,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  possibleBadgeText: {
    fontFamily: fonts.medium,
    fontSize: 11,
    color: authColors.pink,
  },
  possibleCardReason: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: authColors.gray,
    marginTop: 6,
    lineHeight: 18,
  },
  cardNutrients: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
    marginTop: 10,
  },
  sectionLabel: {
    fontFamily: fonts.medium,
    fontSize: 13,
    color: authColors.gray,
    marginTop: 8,
    marginBottom: 2,
  },
  mutedCard: {
    backgroundColor: '#F8F5F4',
    borderRadius: 16,
    padding: 14,
  },
  mutedCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  mutedCardName: {
    fontFamily: fonts.medium,
    fontSize: 13,
    color: authColors.gray,
    flex: 1,
  },
  mutedBadge: {
    backgroundColor: '#EFEAE9',
    borderRadius: 100,
    paddingHorizontal: 9,
    paddingVertical: 3,
  },
  mutedBadgeText: {
    fontFamily: fonts.medium,
    fontSize: 10,
    color: authColors.gray,
  },
  mutedCardReason: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
    marginTop: 4,
    lineHeight: 16,
  },
  alternativeBox: {
    marginTop: 8,
    backgroundColor: authColors.white,
    borderRadius: 10,
    padding: 10,
  },
  alternativeLabel: {
    fontFamily: fonts.regular,
    fontSize: 10,
    color: authColors.gray,
  },
  alternativeName: {
    fontFamily: fonts.medium,
    fontSize: 12,
    color: authColors.pink,
    marginTop: 2,
  },
});
