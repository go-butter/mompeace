import { router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import InformationIcon from '@/assets/images/onboarding/information.svg';
import { authColors } from '@/components/auth/colors';
import { GradientBackground } from '@/components/auth/gradient-background';
import { StepProgressDots } from '@/components/auth/step-progress-dots';
import { NutrientPicker } from '@/components/nutrient-picker';
import { fonts } from '@/constants/fonts';
import { DEFAULT_SELECTED_NUTRIENTS, MAX_SELECTED_NUTRIENTS, SelectableNutrientKey } from '@/constants/nutrients';
import { useAuth } from '@/context/auth-context';
import { ApiError, updateNutrientPreferences } from '@/lib/api-client';

export default function NutrientSelectScreen() {
  const { user } = useAuth();
  const [selected, setSelected] = useState<SelectableNutrientKey[]>(DEFAULT_SELECTED_NUTRIENTS);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMountedRef = useRef(true);
  const isFormValid = selected.length === MAX_SELECTED_NUTRIENTS;

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const handleNext = async () => {
    if (!user?.user_id) {
      setError('사용자 정보를 찾을 수 없습니다. 다시 로그인해 주세요.');
      return;
    }

    setError(null);
    setLoading(true);
    try {
      await updateNutrientPreferences(user.user_id, selected);
      if (!isMountedRef.current) return;
      router.push('/(tabs)/home');
    } catch (err) {
      if (!isMountedRef.current) return;
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError((err as Error).message);
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  };

  return (
    <View style={styles.container}>
      <GradientBackground />

      <ScrollView contentContainerStyle={styles.content}>
        <Image
          source={require('@/assets/images/common/logo_nottext.png')}
          style={styles.logo}
          resizeMode="contain"
        />

        <Text style={styles.title}>
          <Text style={{ color: authColors.pink }}>영양 성분</Text>
          <Text style={{ color: authColors.brown }}>을{'\n'}선택해 주세요</Text>
        </Text>
        <Text style={styles.subtitle}>
          오늘의 섭취 요약에서{'\n'}중점적으로 볼 성분을 골라주세요 :)
        </Text>
        <View style={styles.noteRow}>
          <Text style={styles.caffeineNote}>카페인은 기본으로 포함돼요!</Text>
          <Text>
            <Text style={styles.counterNumber}>{selected.length}</Text>
            <Text style={styles.counterRest}> / {MAX_SELECTED_NUTRIENTS} 선택됨</Text>
          </Text>
        </View>

        <View style={styles.card}>
          <NutrientPicker selected={selected} onChange={setSelected} />

          <View style={styles.banner}>
            <InformationIcon width={18} height={18} />
            <Text style={styles.bannerText}>추후 마이페이지에서 수정 가능해요 :)</Text>
          </View>
        </View>
      </ScrollView>

      <View style={styles.footer}>
        <View style={styles.dotsRow}>
          <StepProgressDots activeStep={2} />
        </View>
        {error && <Text style={styles.errorText}>{error}</Text>}
        <Pressable
          style={[styles.nextButton, (!isFormValid || loading) && styles.buttonDisabled]}
          onPress={handleNext}
          disabled={!isFormValid || loading}>
          <View style={styles.buttonContent}>
            {loading && <ActivityIndicator size="small" color={authColors.white} />}
            <Text style={styles.nextButtonText}>{loading ? '저장 중...' : '완료'}</Text>
          </View>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    paddingHorizontal: 24,
    paddingTop: 90,
    paddingBottom: 24,
  },
  logo: {
    width: 100,
    height: 68,
    opacity: 0.85,
  },
  title: {
    fontSize: 29,
    fontFamily: fonts.bold,
    marginTop: 20,
    lineHeight: 36,
  },
  subtitle: {
    fontSize: 15,
    fontFamily: fonts.regular,
    color: authColors.gray,
    marginTop: 12,
    lineHeight: 22,
  },
  caffeineNote: {
    fontSize: 13,
    fontFamily: fonts.regular,
    color: authColors.gray,
  },
  card: {
    backgroundColor: authColors.white,
    borderRadius: 24,
    padding: 20,
    marginTop: 12,
    borderWidth: 1,
    borderColor: authColors.border,
    // 이전에 완전히 없앴던 그림자를 훨씬 옅은 버전으로 되살림 (기존 neon 스타일보다
    // opacity/blur를 크게 낮춘 은은한 톤).
    shadowColor: authColors.pink,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
    elevation: 2,
  },
  noteRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 16,
  },
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#FFF5F3',
    borderRadius: 12,
    padding: 12,
    marginTop: 20,
  },
  bannerText: {
    fontSize: 12,
    fontFamily: fonts.regular,
    color: authColors.gray,
    flex: 1,
  },
  counterNumber: {
    fontSize: 22,
    fontFamily: fonts.bold,
    color: authColors.pink,
  },
  counterRest: {
    fontSize: 14,
    fontFamily: fonts.medium,
    color: authColors.gray,
  },
  footer: {
    paddingHorizontal: 24,
    paddingBottom: 32,
  },
  dotsRow: {
    alignItems: 'center',
    marginBottom: 16,
  },
  nextButton: {
    backgroundColor: authColors.pink,
    borderRadius: 999,
    paddingVertical: 16,
    alignItems: 'center',
  },
  nextButtonText: {
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
