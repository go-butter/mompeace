import { router } from 'expo-router';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import BarcodeIcon from '@/assets/images/common/tab_barcode.svg';
import SearchIcon from '@/assets/images/scan/search.svg';
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
  const goToBarcodeScan = () => {
    onClose();
    router.push('/(tabs)/scan');
  };

  const goToSearch = () => {
    onClose();
    router.push({ pathname: '/(tabs)/home/food-entry-search', params: { date: selectedDate } });
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable style={styles.sheet} onPress={() => {}}>
          <Text style={styles.title}>음식 추가하기</Text>
          <Text style={styles.subtitle}>오늘 먹은 음식을 편하게 기록해 보세요 :)</Text>

          <View style={styles.buttonRow}>
            <Pressable style={styles.optionButtonPrimary} onPress={goToBarcodeScan}>
              <BarcodeIcon width={31} height={32} />
              <Text style={styles.optionLabelPrimary}>바코드 스캔</Text>
              <Text style={styles.optionDescPrimary}>마트·편의점 상품{'\n'}빠르게 기록</Text>
            </Pressable>

            <Pressable style={styles.optionButton} onPress={goToSearch}>
              <SearchIcon width={32} height={32} />
              <Text style={styles.optionLabel}>음식 검색 및{'\n'}직접 입력</Text>
              <Text style={styles.optionDesc}>카페 음료·식사 메뉴{'\n'}검색/직접 기록</Text>
            </Pressable>
          </View>

          <Pressable style={styles.addButton} onPress={goToSearch}>
            <Text style={styles.addButtonText}>추가하기</Text>
          </Pressable>

          <Pressable onPress={onClose}>
            <Text style={styles.cancelText}>취소하기</Text>
          </Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
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
    textAlign: 'center',
  },
  subtitle: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 15,
    color: authColors.gray,
    marginTop: 16,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 16,
  },
  optionButtonPrimary: {
    flex: 1,
    backgroundColor: '#FFF5F3',
    borderWidth: 1,
    borderColor: authColors.pink,
    borderRadius: 10,
    paddingVertical: 18,
    alignItems: 'center',
    gap: 8,
  },
  optionButton: {
    flex: 1,
    backgroundColor: '#FFF5F3',
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 10,
    paddingVertical: 18,
    alignItems: 'center',
    gap: 8,
  },
  optionLabelPrimary: {
    fontFamily: fonts.medium,
    fontSize: 13,
    color: '#000000',
    textAlign: 'center',
  },
  optionLabel: {
    fontFamily: fonts.medium,
    fontSize: 12,
    color: '#000000',
    textAlign: 'center',
  },
  optionDescPrimary: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 11,
    color: authColors.gray,
    textAlign: 'center',
  },
  optionDesc: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 11,
    color: authColors.gray,
    textAlign: 'center',
  },
  addButton: {
    marginTop: 20,
    backgroundColor: authColors.pink,
    borderRadius: 100,
    height: 51,
    alignItems: 'center',
    justifyContent: 'center',
  },
  addButtonText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 19,
    color: authColors.white,
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
