import { CameraView, useCameraPermissions } from 'expo-camera';
import { router } from 'expo-router';
import { useRef } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import PrevIcon from '@/assets/images/common/prev.svg';
import CautionIcon from '@/assets/images/scan/caution.svg';
import SunIcon from '@/assets/images/scan/sun.svg';
import BarcodeTipIcon from '@/assets/images/scan/caution_barcode_2.svg';
import { authColors } from '@/components/auth/colors';
import { fonts, nanumSquareRound } from '@/constants/fonts';

export default function BarcodeScanStartScreen() {
  const insets = useSafeAreaInsets();
  const [permission, requestPermission] = useCameraPermissions();
  const hasScannedRef = useRef(false);

  const handleBarcodeScanned = (result: { data: string }) => {
    if (hasScannedRef.current) return;
    hasScannedRef.current = true;
    router.push({ pathname: '/(tabs)/scan/result', params: { barcode: result.data } });
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 7 }]}>
      <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
        <PrevIcon width={15} height={15} />
      </Pressable>

      <View style={styles.top}>
        <Text style={styles.title}>바코드 스캔</Text>
        <Text style={styles.subtitle}>
          상품 바코드를 비추면 임신 주차를 기준으로 안전 정보를 확인해 드려요!
        </Text>
      </View>

      <View style={styles.scanCard}>
        <View style={styles.cameraBox}>
          {!permission ? null : !permission.granted ? (
            <View style={styles.permissionPrompt}>
              {permission.canAskAgain ? (
                <>
                  <Text style={styles.permissionText}>
                    바코드를 스캔하려면 카메라 접근 권한이 필요해요.
                  </Text>
                  <Pressable style={styles.permissionButton} onPress={requestPermission}>
                    <Text style={styles.permissionButtonText}>카메라 권한 허용하기</Text>
                  </Pressable>
                </>
              ) : (
                <Text style={styles.permissionText}>
                  카메라 접근이 거부되었어요.{'\n'}기기 설정에서 카메라 권한을 허용해 주세요.
                </Text>
              )}
            </View>
          ) : (
            <CameraView
              style={styles.camera}
              facing="back"
              barcodeScannerSettings={{
                barcodeTypes: ['ean13', 'ean8', 'upc_a', 'upc_e', 'code128'],
              }}
              onBarcodeScanned={handleBarcodeScanned}
            />
          )}
        </View>
        <Text style={styles.scanningText}>스캔 중</Text>
      </View>

      <View style={styles.cautionCard}>
        <View style={styles.cautionHeaderRow}>
          <CautionIcon width={17} height={17} />
          <Text style={styles.cautionTitle}>실제 바코드가 있는 상품만 스캔 가능해요!</Text>
        </View>
        <Text style={styles.cautionBody}>
          수제 음식, 바코드가 없는 제품,{'\n'}흐리거나 손상된 코드는 인식이 어려울 수 있어요!
        </Text>
      </View>

      <View style={styles.tipRow}>
        <View style={styles.tipCard}>
          <SunIcon width={23} height={23} />
          <Text style={styles.tipText}>밝은 곳에서 촬영해 주세요!</Text>
        </View>
        <View style={styles.tipCard}>
          <BarcodeTipIcon width={27} height={27} />
          <Text style={styles.tipText}>바코드가 가려지지 않게{'\n'}맞춰 주세요 :)</Text>
        </View>
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
  prevButton: {
    width: 30,
    height: 29,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 5,
  },
  top: {
    marginTop: 14,
    marginHorizontal: 5,
  },
  title: {
    fontFamily: fonts.medium,
    fontSize: 29,
    color: '#000000',
  },
  subtitle: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 11,
    color: '#4A4A4A',
    marginTop: 8,
    letterSpacing: -0.11,
  },
  scanCard: {
    marginTop: 19,
    backgroundColor: authColors.white,
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 20,
    padding: 20,
    alignItems: 'center',
  },
  cameraBox: {
    width: '100%',
    height: 175,
    borderRadius: 8,
    overflow: 'hidden',
    backgroundColor: '#D9D9D9',
  },
  camera: {
    flex: 1,
  },
  permissionPrompt: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 20,
  },
  permissionText: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: '#4A4A4A',
    textAlign: 'center',
    lineHeight: 18,
  },
  permissionButton: {
    marginTop: 12,
    backgroundColor: authColors.pink,
    borderRadius: 100,
    paddingHorizontal: 18,
    paddingVertical: 10,
  },
  permissionButtonText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 12,
    color: authColors.white,
  },
  scanningText: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 14,
    color: authColors.pink,
    marginTop: 16,
  },
  cautionCard: {
    marginTop: 17,
    backgroundColor: '#FFF5F3',
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 15,
    padding: 18,
  },
  cautionHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  cautionTitle: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 14,
    color: authColors.pink,
  },
  cautionBody: {
    fontFamily: nanumSquareRound.regular,
    fontSize: 12,
    color: '#4A4A4A',
    marginTop: 10,
    lineHeight: 18,
  },
  tipRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 16,
  },
  tipCard: {
    flex: 1,
    backgroundColor: authColors.white,
    borderWidth: 0.7,
    borderColor: authColors.border,
    borderRadius: 11,
    paddingVertical: 14,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  tipText: {
    fontFamily: 'Inter',
    fontSize: 9.5,
    color: '#4A4A4A',
    flex: 1,
    lineHeight: 13,
  },
});
