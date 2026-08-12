import { router, useLocalSearchParams } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import CautionIcon from '@/assets/images/scan/caution.svg';
import { authColors } from '@/components/auth/colors';
import { fonts, nanumSquareRound } from '@/constants/fonts';

export default function FoodEntryOcrFailureScreen() {
  const insets = useSafeAreaInsets();
  const { date } = useLocalSearchParams<{ date: string }>();

  const goRetake = () => {
    router.replace({ pathname: '/(tabs)/food-diary/food-entry-ocr-guide', params: { date } });
  };

  const goSearch = () => {
    router.replace({ pathname: '/(tabs)/food-diary/food-entry-search', params: { date } });
  };

  const goManual = () => {
    router.replace({ pathname: '/(tabs)/food-diary/food-entry-manual', params: { date } });
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 60, paddingBottom: insets.bottom + 24 }]}>
      <View style={styles.iconWrap}>
        <CautionIcon width={34} height={34} />
      </View>
      <Text style={styles.title}>영양성분표를 인식하지 못했어요</Text>
      <Text style={styles.subtitle}>
        라벨이 잘 보이도록 다시 촬영하거나,{'\n'}검색 또는 직접 입력으로 등록해보세요.
      </Text>

      <View style={styles.buttonGroup}>
        <Pressable style={styles.primaryButton} onPress={goRetake}>
          <Text style={styles.primaryButtonText}>다시 촬영하기</Text>
        </Pressable>
        <Pressable style={styles.secondaryButton} onPress={goSearch}>
          <Text style={styles.secondaryButtonText}>검색해서 등록하기</Text>
        </Pressable>
        <Pressable style={styles.secondaryButton} onPress={goManual}>
          <Text style={styles.secondaryButtonText}>직접 입력하기</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: authColors.white,
    paddingHorizontal: 24,
    alignItems: 'center',
  },
  iconWrap: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#FFF0F0',
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontFamily: fonts.semiBold,
    fontSize: 18,
    color: '#000000',
    marginTop: 20,
    textAlign: 'center',
  },
  subtitle: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 13,
    color: authColors.gray,
    marginTop: 10,
    textAlign: 'center',
    lineHeight: 20,
  },
  buttonGroup: {
    width: '100%',
    marginTop: 36,
    gap: 12,
  },
  primaryButton: {
    backgroundColor: authColors.pink,
    borderRadius: 100,
    height: 51,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryButtonText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 16,
    color: authColors.white,
  },
  secondaryButton: {
    backgroundColor: authColors.white,
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 100,
    height: 51,
    alignItems: 'center',
    justifyContent: 'center',
  },
  secondaryButtonText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 15,
    color: '#4A4A4A',
  },
});
