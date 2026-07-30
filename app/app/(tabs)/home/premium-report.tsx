import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import PrevIcon from '@/assets/images/common/prev.svg';
import { authColors } from '@/components/auth/colors';
import { fonts } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import { ApiError, getPremiumStatus } from '@/lib/api-client';

export default function PremiumReportScreen() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const [isPremium, setIsPremium] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user?.user_id) return;
    getPremiumStatus(user.user_id)
      .then((res) => setIsPremium(res.is_premium))
      .catch((err) => setError(err instanceof ApiError ? err.message : (err as Error).message))
      .finally(() => setLoading(false));
  }, [user?.user_id]);

  return (
    <View style={[styles.container, { paddingTop: insets.top + 7 }]}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
          <PrevIcon width={15} height={15} />
        </Pressable>
        <Text style={styles.title}>프리미엄 리포트</Text>
      </View>

      <View style={styles.card}>
        {loading ? (
          <ActivityIndicator size="small" color={authColors.pink} />
        ) : error ? (
          <Text style={styles.errorText}>{error}</Text>
        ) : isPremium ? (
          <Text style={styles.bodyText}>리포트 내용은 추후 제공됩니다.</Text>
        ) : (
          <>
            <Text style={styles.upsellTitle}>프리미엄 회원 전용 기능이에요</Text>
            <Text style={styles.upsellBody}>
              일간·주간 섭취 흐름을 한눈에 보는{'\n'}프리미엄 리포트를 이용해 보세요.
            </Text>
          </>
        )}
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
  card: {
    backgroundColor: authColors.white,
    borderRadius: 25,
    padding: 24,
    marginTop: 20,
    marginHorizontal: 19,
    shadowColor: '#FFEEF0',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 12,
    elevation: 4,
    alignItems: 'center',
  },
  errorText: {
    fontFamily: fonts.regular,
    color: authColors.pink,
    fontSize: 13,
    textAlign: 'center',
  },
  bodyText: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.brown,
    textAlign: 'center',
  },
  upsellTitle: {
    fontFamily: fonts.semiBold,
    fontSize: 15,
    color: authColors.brown,
    textAlign: 'center',
  },
  upsellBody: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
    textAlign: 'center',
    marginTop: 8,
    lineHeight: 20,
  },
});
