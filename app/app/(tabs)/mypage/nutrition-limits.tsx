import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { authColors } from '@/components/auth/colors';
import { fonts } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import { ApiError, getNutritionLimits, NutritionLimitsResponse } from '@/lib/api-client';

const TRIMESTER_ORDER: Array<'early' | 'middle' | 'late'> = ['early', 'middle', 'late'];

function LimitRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.limitRow}>
      <Text style={styles.limitLabel}>{label}</Text>
      <Text style={styles.limitValue}>{value}</Text>
    </View>
  );
}

export default function NutritionLimitsScreen() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const [data, setData] = useState<NutritionLimitsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTrimester, setSelectedTrimester] = useState<'early' | 'middle' | 'late' | null>(null);

  useEffect(() => {
    if (!user?.user_id) return;
    getNutritionLimits(user.user_id)
      .then((res) => {
        setData(res);
        setSelectedTrimester(res.current_trimester);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : (err as Error).message))
      .finally(() => setLoading(false));
  }, [user?.user_id]);

  if (loading) {
    return (
      <View style={[styles.centered, { paddingTop: insets.top }]}>
        <ActivityIndicator size="large" color={authColors.pink} />
      </View>
    );
  }

  if (error || !data || !selectedTrimester) {
    return (
      <View style={[styles.centered, { paddingTop: insets.top }]}>
        <Text style={styles.errorText}>{error || '정보를 불러오지 못했습니다.'}</Text>
      </View>
    );
  }

  const limits = data.trimesters[selectedTrimester];
  const isCurrent = selectedTrimester === data.current_trimester;

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 12 }]}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Ionicons name="chevron-back" size={24} color={authColors.brown} />
        </Pressable>
        <Text style={styles.headerTitle}>초/중/후기별 제한사항</Text>
      </View>

      <View style={styles.tabRow}>
        {TRIMESTER_ORDER.map((key) => {
          const active = key === selectedTrimester;
          return (
            <Pressable
              key={key}
              style={[styles.tab, active && styles.tabActive]}
              onPress={() => setSelectedTrimester(key)}>
              <Text style={[styles.tabText, active && styles.tabTextActive]}>
                {data.trimesters[key].label}
              </Text>
              {key === data.current_trimester && (
                <View style={styles.currentDot} />
              )}
            </Pressable>
          );
        })}
      </View>

      {isCurrent && (
        <View style={styles.currentBanner}>
          <Text style={styles.currentBannerText}>현재 나의 시기예요</Text>
        </View>
      )}

      <View style={styles.card}>
        <Text style={styles.noteText}>{limits.note}</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>1일 기준값</Text>
        <LimitRow label="카페인" value={`${limits.caffeine_mg}mg 이하`} />
        <LimitRow label="당류" value={`${limits.sugar_g}g 이하`} />
        <LimitRow label="나트륨" value={`${limits.sodium_mg}mg 이하`} />
        <LimitRow label="탄수화물" value={`${limits.carbohydrate_g}g 이상`} />
        <LimitRow label="단백질" value={`${limits.protein_g}g 이상`} />
        <LimitRow label="에너지" value={`${limits.energy_kcal}kcal 이상`} />
        <LimitRow
          label="지방"
          value={`총 에너지의 ${Math.round(limits.fat_ratio_min * 100)}~${Math.round(limits.fat_ratio_max * 100)}%`}
        />
        <LimitRow
          label="포화지방"
          value={`총 에너지의 ${Math.round(limits.saturated_fat_ratio_max * 100)}% 미만`}
        />
        <LimitRow
          label="트랜스지방"
          value={`총 에너지의 ${Math.round(limits.trans_fat_ratio_max * 100)}% 미만`}
        />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#FEFAF9',
  },
  content: {
    paddingHorizontal: 19,
    paddingBottom: 40,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FEFAF9',
  },
  errorText: {
    fontFamily: fonts.regular,
    color: authColors.pink,
    fontSize: 14,
    textAlign: 'center',
    paddingHorizontal: 24,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 16,
  },
  headerTitle: {
    fontSize: 18,
    fontFamily: fonts.medium,
    color: authColors.brown,
  },
  tabRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 12,
  },
  tab: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: authColors.border,
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 4,
  },
  tabActive: {
    backgroundColor: authColors.pink,
    borderColor: authColors.pink,
  },
  tabText: {
    fontFamily: fonts.medium,
    fontSize: 13,
    color: authColors.brown,
  },
  tabTextActive: {
    color: authColors.white,
  },
  currentDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: authColors.white,
  },
  currentBanner: {
    backgroundColor: '#FFF5F3',
    borderRadius: 10,
    paddingVertical: 8,
    paddingHorizontal: 12,
    marginBottom: 12,
    alignItems: 'center',
  },
  currentBannerText: {
    fontFamily: fonts.medium,
    fontSize: 12,
    color: authColors.pink,
  },
  card: {
    backgroundColor: authColors.white,
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: authColors.border,
  },
  noteText: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.grayDark,
    lineHeight: 19,
  },
  sectionTitle: {
    fontFamily: fonts.medium,
    fontSize: 14,
    color: authColors.brown,
    marginBottom: 10,
  },
  limitRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: authColors.border,
  },
  limitLabel: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
  },
  limitValue: {
    fontFamily: fonts.medium,
    fontSize: 13,
    color: authColors.brown,
  },
});