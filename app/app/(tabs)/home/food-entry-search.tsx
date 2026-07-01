import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import PrevIcon from '@/assets/images/common/prev.svg';
import { authColors } from '@/components/auth/colors';
import { fonts, nanumSquareRound } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import {
  ApiError,
  createFoodLog,
  FoodSearchResultItem,
  searchFoods,
} from '@/lib/api-client';

function formatNow() {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, '0');
  const dd = String(now.getDate()).padStart(2, '0');
  const hh = String(now.getHours()).padStart(2, '0');
  const min = String(now.getMinutes()).padStart(2, '0');
  const ss = String(now.getSeconds()).padStart(2, '0');
  return { time: `${hh}:${min}:${ss}`, label: `${yyyy}.${mm}.${dd} ${hh}:${min}` };
}

function SearchResultRow({
  item,
  onPress,
}: {
  item: FoodSearchResultItem;
  onPress: () => void;
}) {
  const data = item.data as Record<string, any>;
  return (
    <Pressable style={styles.row} onPress={onPress}>
      <View style={styles.rowTextArea}>
        <View style={styles.rowNameRow}>
          <Text style={styles.rowName}>{data.food_name}</Text>
          {item.source === 'personal' && (
            <View style={styles.personalBadge}>
              <Text style={styles.personalBadgeText}>개인 기록</Text>
            </View>
          )}
        </View>
        <Text style={styles.rowMeta}>
          칼로리 {data.calories_kcal ?? 0}kcal · 당류 {data.sugar_g ?? 0}g · 나트륨{' '}
          {data.sodium_mg ?? 0}mg
        </Text>
      </View>
    </Pressable>
  );
}

export default function FoodEntrySearchScreen() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const { date } = useLocalSearchParams<{ date: string }>();

  const [query, setQuery] = useState('');
  const [results, setResults] = useState<FoodSearchResultItem[]>([]);
  const [searched, setSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [logging, setLogging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runSearch = () => {
    const trimmed = query.trim();
    if (!trimmed || !user?.user_id) return;
    setLoading(true);
    setError(null);
    searchFoods(trimmed, user.user_id, user.pregnancy_week ?? 20)
      .then((res) => {
        setResults(res.results);
        setSearched(true);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : (err as Error).message))
      .finally(() => setLoading(false));
  };

  const handleSelectResult = (item: FoodSearchResultItem) => {
    if (!user?.user_id || !date || logging) return;
    const data = item.data as Record<string, any>;
    const { time } = formatNow();

    setLogging(true);
    setError(null);
    createFoodLog({
      user_id: user.user_id,
      food_name: data.food_name,
      input_type: 'search',
      food_id: item.source === 'personal' ? undefined : item.food_id,
      amount: 1,
      unit: '개',
      caffeine_mg: data.caffeine_mg ?? null,
      sugar_g: data.sugar_g ?? 0,
      sodium_mg: data.sodium_mg ?? 0,
      calories_kcal: data.calories_kcal ?? 0,
      carbohydrate_g: data.carbohydrate_g ?? null,
      protein_g: data.protein_g ?? null,
      eaten_at: `${date} ${time}`,
    })
      .then(() => {
        router.replace('/(tabs)/home/food-diary');
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : (err as Error).message);
      })
      .finally(() => setLogging(false));
  };

  const goToManualEntry = () => {
    router.push({
      pathname: '/(tabs)/home/food-entry-manual',
      params: { date: date ?? '', name: query.trim() },
    });
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 7, paddingBottom: insets.bottom }]}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
          <PrevIcon width={15} height={15} />
        </Pressable>
        <Text style={styles.title}>음식 검색</Text>
      </View>

      <View style={styles.searchRow}>
        <TextInput
          style={styles.searchInput}
          value={query}
          onChangeText={setQuery}
          placeholder="예: 아메리카노"
          placeholderTextColor={authColors.gray}
          returnKeyType="search"
          onSubmitEditing={runSearch}
        />
        <Pressable style={styles.searchButton} onPress={runSearch}>
          <Text style={styles.searchButtonText}>검색</Text>
        </Pressable>
      </View>

      {error && <Text style={styles.errorText}>{error}</Text>}

      <View style={styles.resultsArea}>
        {loading ? (
          <View style={styles.loadingArea}>
            <ActivityIndicator size="small" color={authColors.pink} />
          </View>
        ) : (
          <FlatList
            style={styles.list}
            data={results}
            keyExtractor={(item, index) => `${item.source}-${item.food_id}-${index}`}
            renderItem={({ item }) => (
              <SearchResultRow item={item} onPress={() => handleSelectResult(item)} />
            )}
            ListEmptyComponent={
              searched ? <Text style={styles.emptyText}>검색 결과가 없어요.</Text> : null
            }
          />
        )}
      </View>

      <Pressable style={styles.manualButton} onPress={goToManualEntry}>
        <Text style={styles.manualButtonText}>직접 입력하기</Text>
      </Pressable>
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
  searchRow: {
    flexDirection: 'row',
    gap: 8,
    paddingHorizontal: 19,
    marginTop: 16,
  },
  searchInput: {
    flex: 1,
    backgroundColor: authColors.white,
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 15,
    height: 44,
    paddingHorizontal: 16,
    fontSize: 13,
    color: '#000000',
  },
  searchButton: {
    backgroundColor: authColors.pink,
    borderRadius: 15,
    height: 44,
    paddingHorizontal: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  searchButtonText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 13,
    color: authColors.white,
  },
  errorText: {
    fontFamily: fonts.regular,
    color: authColors.pink,
    fontSize: 12,
    textAlign: 'center',
    marginTop: 12,
    paddingHorizontal: 19,
  },
  resultsArea: {
    flex: 1,
    marginTop: 12,
  },
  loadingArea: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  list: {
    flex: 1,
    paddingHorizontal: 19,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 16,
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 10,
    marginBottom: 8,
  },
  rowTextArea: {
    flex: 1,
  },
  rowNameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  rowName: {
    fontFamily: fonts.medium,
    fontSize: 14,
    color: authColors.brown,
  },
  personalBadge: {
    backgroundColor: '#F5F5F5',
    borderRadius: 100,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  personalBadgeText: {
    fontFamily: fonts.medium,
    fontSize: 10,
    color: authColors.gray,
  },
  rowMeta: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
    marginTop: 4,
  },
  emptyText: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
    textAlign: 'center',
    paddingVertical: 24,
  },
  manualButton: {
    marginHorizontal: 19,
    marginBottom: 24,
    marginTop: 8,
    borderWidth: 1,
    borderColor: authColors.pink,
    borderRadius: 100,
    height: 48,
    alignItems: 'center',
    justifyContent: 'center',
  },
  manualButtonText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 14,
    color: authColors.pink,
  },
});
