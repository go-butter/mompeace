import { router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import PrevIcon from '@/assets/images/common/prev.svg';
import { authColors } from '@/components/auth/colors';
import { ALLERGEN_OPTIONS } from '@/constants/allergens';
import { fonts } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import { ApiError, updateAllergyInfo } from '@/lib/api-client';

function parseStoredAllergies(allergyInfo: string | null | undefined): string[] {
  if (!allergyInfo) return [];
  return allergyInfo
    .split(',')
    .map((item) => item.trim())
    .filter((item) => (ALLERGEN_OPTIONS as readonly string[]).includes(item));
}

export default function EditAllergyScreen() {
  const insets = useSafeAreaInsets();
  const { user, login } = useAuth();
  const [selected, setSelected] = useState<string[]>(() => parseStoredAllergies(user?.allergy_info));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleAllergen = (item: string) => {
    setSelected((prev) =>
      prev.includes(item) ? prev.filter((selectedItem) => selectedItem !== item) : [...prev, item]
    );
  };

  const handleSave = async () => {
    if (!user?.user_id) {
      setError('사용자 정보를 찾을 수 없습니다. 다시 로그인해 주세요.');
      return;
    }

    setError(null);
    setLoading(true);
    try {
      const allergyInfo = selected.join(',');
      const response = await updateAllergyInfo(user.user_id, { allergy_info: allergyInfo });
      login({ ...user, allergy_info: response.allergy_info });
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
        <Text style={styles.title}>알레르기 정보 수정</Text>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.subtitle}>해당하는 알레르기 유발물질을 모두 선택해 주세요</Text>
        <View style={styles.card}>
          <View style={styles.chipWrap}>
            {ALLERGEN_OPTIONS.map((item) => {
              const isSelected = selected.includes(item);
              return (
                <Pressable
                  key={item}
                  style={[styles.chip, isSelected && styles.chipSelected]}
                  onPress={() => toggleAllergen(item)}>
                  <Text style={[styles.chipText, isSelected && styles.chipTextSelected]}>
                    {item}
                  </Text>
                </Pressable>
              );
            })}
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
    backgroundColor: authColors.white,
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
  subtitle: {
    fontSize: 13,
    fontFamily: fonts.regular,
    color: authColors.gray,
    marginBottom: 16,
  },
  card: {
    backgroundColor: authColors.white,
    borderRadius: 24,
    padding: 20,
    shadowColor: authColors.pink,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.18,
    shadowRadius: 24,
    elevation: 6,
  },
  chipWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  chip: {
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 999,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  chipSelected: {
    backgroundColor: authColors.pink,
    borderColor: authColors.pink,
  },
  chipText: {
    fontSize: 14,
    fontFamily: fonts.regular,
    color: authColors.brown,
  },
  chipTextSelected: {
    color: authColors.white,
    fontFamily: fonts.medium,
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
