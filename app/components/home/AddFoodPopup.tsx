import { router } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import CoffeeIcon from '@/assets/images/common/coffee.svg';
import OcrScanIcon from '@/assets/images/common/ocr_scan.svg';
import ManualEntryIcon from '@/assets/images/mypage/mypage_edit_information.svg';
import SearchIcon from '@/assets/images/scan/search.svg';
import BottomSheet from '@/components/common/BottomSheet';
import OptionCard from '@/components/home/OptionCard';
import { authColors } from '@/components/auth/colors';
import { fonts, nanumSquareRound } from '@/constants/fonts';

export default function AddFoodPopup({
  visible,
  onClose,
  selectedDate,
}: {
  visible: boolean;
  onClose: () => void;
  selectedDate: string;
}) {
  const insets = useSafeAreaInsets();

  const goToSearch = () => {
    onClose();
    router.push({ pathname: '/(tabs)/food-diary/food-entry-search', params: { date: selectedDate } });
  };

  const goToManualEntry = () => {
    onClose();
    router.push({ pathname: '/(tabs)/food-diary/food-entry-manual', params: { date: selectedDate } });
  };

  const goToCoffeeCalculator = () => {
    onClose();
    router.push({ pathname: '/(tabs)/food-diary/food-entry-coffee', params: { date: selectedDate } });
  };

  const goToOcrScan = () => {
    onClose();
    router.push({ pathname: '/(tabs)/food-diary/food-entry-ocr-guide', params: { date: selectedDate } });
  };

  const d = new Date();
  const todayLocal = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const isToday = selectedDate === todayLocal;
  const subtitle = isToday
    ? '먹은 음식을 편하게 기록해 보세요 :)'
    : '그날 먹은 음식을 편하게 기록해 보세요 :)';

  return (
    <BottomSheet visible={visible} onClose={onClose}>
      <View style={[styles.sheet, { paddingBottom: styles.sheet.paddingBottom + insets.bottom }]}>
        <Text style={styles.title}>새 식사 기록하기</Text>
        <Text style={styles.subtitle}>{subtitle}</Text>

        <View style={styles.buttonRow}>
          <OptionCard
            icon={<OcrScanIcon width={31} height={31} color={authColors.pink} />}
            label="영양성분표 스캔"
            description={'포장식품 라벨\n촬영으로 기록'}
            onPress={goToOcrScan}
          />
          <OptionCard
            icon={<CoffeeIcon width={30} height={30} color={authColors.pink} />}
            label="커피 계산하기"
            description={'브랜드 메뉴·홈메이드\n커피로 카페인 확인'}
            onPress={goToCoffeeCalculator}
          />
        </View>

        <View style={styles.buttonRow}>
          <OptionCard
            icon={<SearchIcon width={32} height={32} />}
            label="음식 검색하기"
            description={'카페 음료·식사 메뉴\n검색해서 기록'}
            onPress={goToSearch}
          />
          <OptionCard
            icon={<ManualEntryIcon width={30} height={30} />}
            label="직접 입력하기"
            description={'메뉴가 없을 때\n직접 입력'}
            onPress={goToManualEntry}
          />
        </View>

        <Pressable onPress={onClose}>
          <Text style={styles.cancelText}>취소하기</Text>
        </Pressable>
      </View>
    </BottomSheet>
  );
}

const styles = StyleSheet.create({
  sheet: {
    backgroundColor: authColors.white,
    borderTopLeftRadius: 30,
    borderTopRightRadius: 30,
    paddingTop: 36,
    paddingHorizontal: 19,
    paddingBottom: 40,
  },
  title: {
    fontFamily: fonts.medium,
    fontSize: 25,
    color: '#000000',
    textAlign: 'left',
  },
  subtitle: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 15,
    color: authColors.gray,
    marginTop: 8,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 16,
  },
  cancelText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 15,
    color: authColors.pink,
    textAlign: 'center',
    marginTop: 20,
    textDecorationLine: 'underline',
  },
});
