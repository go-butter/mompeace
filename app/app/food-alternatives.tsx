import { router, useLocalSearchParams } from 'expo-router';
import { useMemo } from 'react';
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import PrevIcon from '@/assets/images/common/prev.svg';
import { authColors } from '@/components/auth/colors';
import { fonts } from '@/constants/fonts';
import { NUTRIENT_LABELS_KO, SelectableNutrientKey } from '@/constants/nutrients';
import { formatNutrient } from '@/lib/format';
import { OcrAlternativeItem } from '@/lib/api-client';

function formatAlternativeNutrients(item: OcrAlternativeItem) {
  return (
    `칼로리 ${formatNutrient(item.calories_kcal, 'kcal')} · ` +
    `당류 ${formatNutrient(item.sugar_g, 'g')} · ` +
    `나트륨 ${formatNutrient(item.sodium_mg, 'mg')} · ` +
    `지방 ${formatNutrient(item.fat_g, 'g')} · ` +
    `철분 ${formatNutrient(item.iron_mg, 'mg')}`
  );
}

function AlternativeRow({ item }: { item: OcrAlternativeItem }) {
  return (
    <View style={styles.dishRow}>
      <Text style={styles.rowName}>{item.food_name}</Text>
      <Text style={styles.rowMeta}>{formatAlternativeNutrients(item)}</Text>
    </View>
  );
}

export default function FoodAlternativesScreen() {
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{
    trigger_nutrient?: string;
    category?: string;
    subcategory?: string;
    product_name?: string;
    alternatives?: string;
  }>();

  const alternatives = useMemo<OcrAlternativeItem[]>(() => {
    if (!params.alternatives) return [];
    try {
      return JSON.parse(params.alternatives) as OcrAlternativeItem[];
    } catch {
      return [];
    }
  }, [params.alternatives]);

  const triggerLabel = params.trigger_nutrient
    ? NUTRIENT_LABELS_KO[params.trigger_nutrient as SelectableNutrientKey]
    : null;

  return (
    <View style={[styles.container, { paddingTop: insets.top + 7, paddingBottom: insets.bottom }]}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
          <PrevIcon width={15} height={15} />
        </Pressable>
        <Text style={styles.title}>대체 메뉴</Text>
      </View>

      <View style={styles.banner}>
        <Text style={styles.bannerText}>
          {params.product_name ? `${params.product_name}의 ` : ''}
          {triggerLabel ? `${triggerLabel} 수치가 높아요. ` : ''}
          {params.subcategory ? `같은 ${params.subcategory} 중 더 나은 대안을 찾아봤어요.` : '대체 메뉴를 찾아봤어요.'}
        </Text>
      </View>

      <FlatList
        style={styles.list}
        data={alternatives}
        keyExtractor={(item) => String(item.food_id)}
        renderItem={({ item }) => <AlternativeRow item={item} />}
        ListEmptyComponent={<Text style={styles.emptyText}>대체 메뉴를 찾지 못했어요.</Text>}
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
  banner: {
    backgroundColor: authColors.pinkLight,
    borderRadius: 12,
    padding: 14,
    marginHorizontal: 19,
    marginTop: 16,
  },
  bannerText: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: authColors.pink,
    lineHeight: 17,
  },
  list: {
    flex: 1,
    marginTop: 12,
    paddingHorizontal: 19,
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
  rowName: {
    fontFamily: fonts.medium,
    fontSize: 14,
    color: '#333333',
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
});
