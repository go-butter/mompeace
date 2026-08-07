import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import PrevIcon from '@/assets/images/common/prev.svg';
import { authColors } from '@/components/auth/colors';
import { NutrientPicker } from '@/components/nutrient-picker';
import { fonts } from '@/constants/fonts';
import { MAX_SELECTED_NUTRIENTS, SelectableNutrientKey } from '@/constants/nutrients';
import { useAuth } from '@/context/auth-context';
import { ApiError, updateNutrientPreferences } from '@/lib/api-client';

export default function NutrientPreferencesScreen() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const [selected, setSelected] = useState<SelectableNutrientKey[]>([]);
  const [loadingCurrent, setLoadingCurrent] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user?.user_id) return;
    // selected_nutrients=null이면 값을 바꾸지 않고 현재 선택을 그대로 돌려주므로,
    // 이 엔드포인트를 그대로 "조회"용으로도 재사용한다.
    updateNutrientPreferences(user.user_id, null)
      .then((response) => setSelected(response.selected_nutrients as SelectableNutrientKey[]))
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : (err as Error).message);
      })
      .finally(() => setLoadingCurrent(false));
  }, [user?.user_id]);

  const handleSave = async () => {
    if (!user?.user_id) {
      setError('사용자 정보를 찾을 수 없습니다. 다시 로그인해 주세요.');
      return;
    }

    setError(null);
    setSaving(true);
    try {
      await updateNutrientPreferences(user.user_id, selected);
      router.back();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 7 }]}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
          <PrevIcon width={15} height={15} />
        </Pressable>
        <Text style={styles.title}>영양성분 선택하기</Text>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.card}>
          <Text style={styles.description}>
            카페인과 물은 항상 표시돼요{'\n'}그 외 {MAX_SELECTED_NUTRIENTS}개를 선택할 수 있어요
          </Text>
          {loadingCurrent ? (
            <ActivityIndicator color={authColors.pink} style={styles.loadingIndicator} />
          ) : (
            <NutrientPicker selected={selected} onChange={setSelected} />
          )}
        </View>
      </ScrollView>

      <View style={styles.footer}>
        {error && <Text style={styles.errorText}>{error}</Text>}
        <Pressable
          style={[styles.saveButton, (saving || loadingCurrent) && styles.buttonDisabled]}
          onPress={handleSave}
          disabled={saving || loadingCurrent}>
          <View style={styles.buttonContent}>
            {saving && <ActivityIndicator size="small" color={authColors.white} />}
            <Text style={styles.saveButtonText}>{saving ? '저장 중...' : '저장'}</Text>
          </View>
        </Pressable>
      </View>
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
  content: {
    paddingHorizontal: 24,
    paddingTop: 20,
    paddingBottom: 24,
  },
  card: {
    backgroundColor: authColors.white,
    borderRadius: 24,
    padding: 20,
    borderWidth: 1,
    borderColor: authColors.border,
  },
  description: {
    fontSize: 14,
    fontFamily: fonts.regular,
    color: authColors.gray,
    lineHeight: 20,
    marginBottom: 16,
  },
  loadingIndicator: {
    marginVertical: 12,
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
