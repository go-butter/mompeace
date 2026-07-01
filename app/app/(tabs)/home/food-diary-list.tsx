import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import PrevIcon from '@/assets/images/common/prev.svg';
import DownIcon from '@/assets/images/common/down.svg';
import UpIcon from '@/assets/images/common/up.svg';
import XIcon from '@/assets/images/common/x.svg';
import { authColors } from '@/components/auth/colors';
import { fonts } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import { useIntake } from '@/context/intake-context';
import { ApiError, deleteFoodLog, FoodLogEntry } from '@/lib/api-client';

function FoodDiaryRow({
  entry,
  expanded,
  onToggle,
  onDelete,
}: {
  entry: FoodLogEntry;
  expanded: boolean;
  onToggle: () => void;
  onDelete: (entry: FoodLogEntry) => void;
}) {
  return (
    <View style={styles.row}>
      <View style={styles.rowHeader}>
        <Text style={styles.rowTime}>{entry.time}</Text>
        <Text style={styles.rowFoodName}>{entry.food_name}</Text>
        <Text style={styles.rowKcal}>
          {entry.calories_kcal != null ? `${entry.calories_kcal}kcal` : ''}
        </Text>
        <Pressable
          onPress={() => onDelete(entry)}
          hitSlop={8}
          style={styles.deleteButton}>
          <XIcon width={19} height={19} color={authColors.pink} />
        </Pressable>
        <Pressable onPress={onToggle} hitSlop={8}>
          {expanded ? (
            <UpIcon width={19} height={19} />
          ) : (
            <DownIcon width={19} height={19} />
          )}
        </Pressable>
      </View>
      {expanded && (
        <View style={styles.rowDetail}>
          <Text style={styles.rowDetailText}>
            칼로리 {entry.calories_kcal ?? 0}kcal · 당류 {entry.sugar_g}g · 나트륨{' '}
            {entry.sodium_mg}mg · 단백질 {entry.protein_g}g
          </Text>
          {entry.allergens.length > 0 && (
            <Text style={styles.rowAllergyText}>알레르기: {entry.allergens.join(', ')}</Text>
          )}
          {entry.extra_nutrients?.length > 0 && (
            <Text style={styles.rowDetailText}>
              추가 성분:{' '}
              {entry.extra_nutrients
                .map((en) => `${en.name} ${en.value}${en.unit ?? ''}`)
                .join(', ')}
            </Text>
          )}
        </View>
      )}
    </View>
  );
}

export default function FoodDiaryListScreen() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const { allFoodLog, refresh } = useIntake();
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  const handleDelete = (entry: FoodLogEntry) => {
    Alert.alert('기록 삭제', `'${entry.food_name}' 기록을 삭제할까요?`, [
      { text: '취소', style: 'cancel' },
      {
        text: '삭제',
        style: 'destructive',
        onPress: () => {
          if (!user?.user_id) return;
          deleteFoodLog(entry.log_id, user.user_id)
            .then(() => refresh())
            .catch((err) => {
              const message = err instanceof ApiError ? err.message : (err as Error).message;
              Alert.alert('삭제 실패', message);
            });
        },
      },
    ]);
  };

  const toggleRow = (logId: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(logId)) {
        next.delete(logId);
      } else {
        next.add(logId);
      }
      return next;
    });
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 7 }]}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
          <PrevIcon width={15} height={15} />
        </Pressable>
        <Text style={styles.title}>오늘 먹은 음식</Text>
      </View>

      <View style={styles.card}>
        {allFoodLog.length === 0 ? (
          <Text style={styles.emptyText}>오늘 기록된 음식이 없어요.</Text>
        ) : (
          allFoodLog.map((entry) => (
            <FoodDiaryRow
              key={entry.log_id}
              entry={entry}
              expanded={expandedIds.has(entry.log_id)}
              onToggle={() => toggleRow(entry.log_id)}
              onDelete={handleDelete}
            />
          ))
        )}
      </View>
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
    paddingBottom: 40,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginTop: 7,
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
    marginTop: 20,
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 10,
    paddingHorizontal: 16,
  },
  emptyText: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
    textAlign: 'center',
    paddingVertical: 24,
  },
  row: {
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: authColors.border,
  },
  rowHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  rowTime: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
    width: 44,
  },
  rowFoodName: {
    fontFamily: fonts.medium,
    fontSize: 12,
    color: '#000000',
    flex: 1,
  },
  rowKcal: {
    fontFamily: fonts.medium,
    fontSize: 12,
    color: authColors.gray,
  },
  deleteButton: {
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowDetail: {
    marginTop: 8,
    paddingLeft: 54,
  },
  rowDetailText: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: '#4A4A4A',
    lineHeight: 16,
  },
  rowAllergyText: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.pink,
    marginTop: 4,
  },
});
