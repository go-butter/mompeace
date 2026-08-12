import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import {
  ActivityIndicator,
  Dimensions,
  FlatList,
  Keyboard,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { ScrollView } from 'react-native-gesture-handler';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import PrevIcon from '@/assets/images/common/prev.svg';
import DownIcon from '@/assets/images/common/down.svg';
import UpIcon from '@/assets/images/common/up.svg';
import CheckboxCheckedIcon from '@/assets/images/common/checkbox_checked.svg';
import CheckboxUncheckedIcon from '@/assets/images/common/checkbox_unchecked.svg';
import CartIcon from '@/assets/images/foodDiary/cart.svg';
import XIcon from '@/assets/images/common/x.svg';
import { authColors } from '@/components/auth/colors';
import BottomSheet from '@/components/common/BottomSheet';
import { fonts, nanumSquareRound } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import { formatNutrient } from '@/lib/format';
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

function getResultKey(item: FoodSearchResultItem, index: number) {
  return `${item.source}-${item.food_id}-${index}`;
}

const CART_SHEET_MAX_HEIGHT_RATIO = 0.72;

function formatCoreNutrients(data: Record<string, any>) {
  return (
    `칼로리 ${formatNutrient(data.calories_kcal, 'kcal')} · ` +
    `탄수화물 ${formatNutrient(data.carbohydrate_g, 'g')} · ` +
    `당류 ${formatNutrient(data.sugar_g, 'g')} · ` +
    `지방 ${formatNutrient(data.fat_g, 'g')} · ` +
    `철분 ${formatNutrient(data.iron_mg, 'mg')} · ` +
    `단백질 ${formatNutrient(data.protein_g, 'g')} · ` +
    `나트륨 ${formatNutrient(data.sodium_mg, 'mg')}`
  );
}

function formatExtraNutrients(data: Record<string, any>) {
  return (
    `포화지방 ${formatNutrient(data.saturated_fat_g, 'g')} · ` +
    `트랜스지방 ${formatNutrient(data.trans_fat_g, 'g')} · ` +
    `콜레스테롤 ${formatNutrient(data.cholesterol_mg, 'mg')}`
  );
}

function SearchResultRow({
  item,
  expanded,
  checked,
  onToggleExpand,
  onToggleCart,
  onAdd,
}: {
  item: FoodSearchResultItem;
  expanded: boolean;
  checked: boolean;
  onToggleExpand: () => void;
  onToggleCart: () => void;
  onAdd: () => void;
}) {
  const data = item.data as Record<string, any>;

  if (item.source !== 'dish_db_download') {
    return (
      <View style={styles.dishRow}>
        <View style={styles.dishRowHeader}>
          <Pressable style={styles.rowMainArea} onPress={onAdd}>
            <View style={styles.rowTextArea}>
              <View style={styles.rowNameRow}>
                <Text style={styles.rowName}>{data.food_name}</Text>
                <View style={styles.personalBadge}>
                  <Text style={styles.personalBadgeText}>개인 기록</Text>
                </View>
              </View>
              <Text style={styles.rowMeta}>{formatCoreNutrients(data)}</Text>
            </View>
          </Pressable>
          <Pressable style={styles.personalExpandButton} onPress={onToggleExpand} hitSlop={8}>
            {expanded ? (
              <UpIcon width={16} height={16} />
            ) : (
              <DownIcon width={16} height={16} />
            )}
          </Pressable>
        </View>
        {expanded && (
          <View style={styles.rowDetail}>
            <Text style={styles.rowDetailText}>{formatExtraNutrients(data)}</Text>
          </View>
        )}
      </View>
    );
  }

  return (
    <View style={styles.dishRow}>
      <View style={styles.dishRowHeader}>
        <Pressable style={styles.checkboxButton} onPress={onToggleCart} hitSlop={8}>
          {checked ? (
            <CheckboxCheckedIcon width={19} height={19} />
          ) : (
            <CheckboxUncheckedIcon width={19} height={19} />
          )}
        </Pressable>
        <Pressable style={styles.rowMainArea} onPress={onToggleExpand}>
          <View style={styles.rowTextArea}>
            <Text style={[styles.rowName, styles.dishRowName]}>{data.food_name}</Text>
            <Text style={styles.rowMeta}>{formatCoreNutrients(data)}</Text>
          </View>
          {expanded ? (
            <UpIcon width={16} height={16} />
          ) : (
            <DownIcon width={16} height={16} />
          )}
        </Pressable>
      </View>
      {expanded && (
        <View style={styles.rowDetail}>
          <Text style={styles.rowDetailText}>{formatExtraNutrients(data)}</Text>
        </View>
      )}
    </View>
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
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [cart, setCart] = useState<Map<string, FoodSearchResultItem>>(new Map());
  const [sheetVisible, setSheetVisible] = useState(false);

  // Numeric (not percentage) so it resolves reliably regardless of how the
  // BottomSheet's own ancestor chain sizes itself — percentage heights need a
  // definite-size ancestor to resolve against, which this one doesn't have.
  const maxSheetHeight = Dimensions.get('window').height * CART_SHEET_MAX_HEIGHT_RATIO - insets.bottom;
  // ScrollView needs its own explicit maxHeight to render at all — flexShrink alone
  // gives it nothing to shrink from inside a maxHeight-bounded (not fixed-height)
  // parent, and it collapses to 0. Budget = the sheet's own cap minus everything
  // inside cartSheet that isn't the list (padding + title block), derived from the
  // style object itself so it can't drift out of sync with the actual layout.
  const cartSheetNonScrollHeight =
    styles.cartSheet.paddingTop +
    (styles.cartSheetTitle.lineHeight as number) +
    (styles.cartSheetTitle.marginBottom as number) +
    styles.cartSheet.paddingBottom;
  const cartSheetListMaxHeight = maxSheetHeight - cartSheetNonScrollHeight - insets.bottom;

  const toggleExpanded = (key: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const toggleCart = (key: string, item: FoodSearchResultItem) => {
    setCart((prev) => {
      const next = new Map(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.set(key, item);
      }
      return next;
    });
  };

  const removeFromCart = (key: string) => {
    setCart((prev) => {
      const next = new Map(prev);
      next.delete(key);
      return next;
    });
  };

  const runSearch = () => {
    const trimmed = query.trim();
    if (!trimmed || !user?.user_id) return;
    setLoading(true);
    setError(null);
    setExpandedIds(new Set());
    searchFoods(trimmed, user.user_id)
      .then((res) => {
        setResults(res.results);
        setSearched(true);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : (err as Error).message))
      .finally(() => setLoading(false));
  };

  const handleSelectResult = (item: FoodSearchResultItem) => {
    Keyboard.dismiss();
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
      calories_kcal: data.calories_kcal ?? null,
      carbohydrate_g: data.carbohydrate_g ?? null,
      protein_g: data.protein_g ?? null,
      fat_g: data.fat_g ?? null,
      iron_mg: data.iron_mg ?? null,
      eaten_at: `${date} ${time}`,
    })
      .then(() => {
        router.dismissTo('/(tabs)/food-diary');
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : (err as Error).message);
      })
      .finally(() => setLogging(false));
  };

  const handleAddCart = () => {
    Keyboard.dismiss();
    if (!user?.user_id || !date || logging || cart.size === 0) return;
    const { time } = formatNow();
    const eatenAt = `${date} ${time}`;

    setLogging(true);
    setError(null);
    Promise.all(
      [...cart.values()].map((item) => {
        const data = item.data as Record<string, any>;
        return createFoodLog({
          user_id: user.user_id,
          food_name: data.food_name,
          input_type: 'search',
          food_id: item.food_id,
          amount: 1,
          unit: '개',
          caffeine_mg: data.caffeine_mg ?? null,
          sugar_g: data.sugar_g ?? 0,
          sodium_mg: data.sodium_mg ?? 0,
          calories_kcal: data.calories_kcal ?? null,
          carbohydrate_g: data.carbohydrate_g ?? null,
          protein_g: data.protein_g ?? null,
          fat_g: data.fat_g ?? null,
          iron_mg: data.iron_mg ?? null,
          eaten_at: eatenAt,
        });
      })
    )
      .then(() => {
        router.dismissTo('/(tabs)/food-diary');
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : (err as Error).message);
      })
      .finally(() => setLogging(false));
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
            keyExtractor={(item, index) => getResultKey(item, index)}
            renderItem={({ item, index }) => {
              const key = getResultKey(item, index);
              return (
                <SearchResultRow
                  item={item}
                  expanded={expandedIds.has(key)}
                  checked={cart.has(key)}
                  onToggleExpand={() => toggleExpanded(key)}
                  onToggleCart={() => toggleCart(key, item)}
                  onAdd={() => handleSelectResult(item)}
                />
              );
            }}
            ListEmptyComponent={
              searched ? <Text style={styles.emptyText}>검색 결과가 없어요.</Text> : null
            }
          />
        )}
      </View>

      <View style={styles.footerRow}>
        <Pressable
          style={[styles.confirmButton, (cart.size === 0 || logging) && styles.confirmButtonDisabled]}
          onPress={handleAddCart}
          disabled={cart.size === 0 || logging}>
          <Text style={styles.confirmButtonText}>{logging ? '추가 중...' : '추가하기'}</Text>
        </Pressable>
        <Pressable
          style={[styles.cartButton, { opacity: cart.size > 0 ? 1 : 0 }]}
          onPress={() => setSheetVisible(true)}
          hitSlop={8}
          pointerEvents={cart.size > 0 ? 'auto' : 'none'}>
          <CartIcon width={18} height={18} />
          <View style={styles.cartBadge}>
            <Text style={styles.cartBadgeText}>{cart.size}</Text>
          </View>
        </Pressable>
      </View>

      <BottomSheet visible={sheetVisible} onClose={() => setSheetVisible(false)}>
        <View
          style={[
            styles.cartSheet,
            { maxHeight: maxSheetHeight, paddingBottom: styles.cartSheet.paddingBottom + insets.bottom },
          ]}>
          <Text style={styles.cartSheetTitle}>담은 음식</Text>
          <ScrollView
            style={[styles.cartSheetList, { maxHeight: cartSheetListMaxHeight }]}
            showsVerticalScrollIndicator={true}>
            {[...cart.entries()].map(([key, item]) => {
              const data = item.data as Record<string, any>;
              return (
                <View key={key} style={styles.cartSheetRow}>
                  <Text style={styles.cartSheetItemName}>{data.food_name}</Text>
                  <Pressable onPress={() => removeFromCart(key)} hitSlop={8}>
                    <XIcon width={16} height={16} color={authColors.gray} />
                  </Pressable>
                </View>
              );
            })}
            {cart.size === 0 && <Text style={styles.cartSheetEmpty}>담은 음식이 없어요.</Text>}
          </ScrollView>
        </View>
      </BottomSheet>
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
  cartButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: authColors.pinkLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cartBadge: {
    position: 'absolute',
    top: -4,
    right: -4,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    paddingHorizontal: 4,
    backgroundColor: authColors.pink,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cartBadgeText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 10,
    color: authColors.white,
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
  dishRowName: {
    color: '#333333',
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
  dishRow: {
    paddingVertical: 12,
    paddingHorizontal: 16,
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 10,
    marginBottom: 8,
  },
  dishRowHeader: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  checkboxButton: {
    marginRight: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  personalExpandButton: {
    marginLeft: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowMainArea: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  rowDetail: {
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: authColors.border,
  },
  rowDetailText: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.grayDark,
    lineHeight: 16,
  },
  emptyText: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
    textAlign: 'center',
    paddingVertical: 24,
  },
  footerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginHorizontal: 19,
    marginBottom: 24,
    marginTop: 8,
  },
  confirmButton: {
    flex: 1,
    backgroundColor: authColors.pink,
    borderRadius: 100,
    height: 48,
    alignItems: 'center',
    justifyContent: 'center',
  },
  confirmButtonDisabled: {
    opacity: 0.6,
  },
  confirmButtonText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 14,
    color: authColors.white,
  },
  cartSheet: {
    backgroundColor: authColors.white,
    borderTopLeftRadius: 30,
    borderTopRightRadius: 30,
    paddingTop: 24,
    paddingHorizontal: 19,
    paddingBottom: 24,
    overflow: 'hidden',
  },
  cartSheetTitle: {
    fontFamily: fonts.semiBold,
    fontSize: 17,
    lineHeight: 20,
    color: authColors.brown,
    marginBottom: 8,
  },
  cartSheetList: {
    flexShrink: 1,
  },
  cartSheetRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: authColors.border,
  },
  cartSheetItemName: {
    fontFamily: fonts.medium,
    fontSize: 13,
    color: '#333333',
  },
  cartSheetEmpty: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
    textAlign: 'center',
    paddingVertical: 20,
  },
});
