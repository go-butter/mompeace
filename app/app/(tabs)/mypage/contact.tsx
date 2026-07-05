import * as Clipboard from 'expo-clipboard';
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import PrevIcon from '@/assets/images/common/prev.svg';
import { authColors } from '@/components/auth/colors';
import { fonts } from '@/constants/fonts';

const CONTACT_EMAIL = 'gobitterbutter@gmail.com';

export default function ContactScreen() {
  const insets = useSafeAreaInsets();
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await Clipboard.setStringAsync(CONTACT_EMAIL);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 7 }]}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
          <PrevIcon width={15} height={15} />
        </Pressable>
        <Text style={styles.title}>문의하기</Text>
      </View>

      <View style={styles.content}>
        <Text style={styles.label}>문의사항은 아래 이메일로 보내주세요</Text>
        <Text style={styles.email}>{CONTACT_EMAIL}</Text>
        <Pressable style={styles.copyButton} onPress={handleCopy}>
          <Text style={styles.copyButtonText}>{copied ? '복사됨!' : '이메일 복사'}</Text>
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
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  label: {
    fontFamily: fonts.regular,
    fontSize: 14,
    color: authColors.gray,
    marginBottom: 12,
  },
  email: {
    fontFamily: fonts.semiBold,
    fontSize: 20,
    color: authColors.brown,
    marginBottom: 24,
  },
  copyButton: {
    backgroundColor: authColors.pink,
    borderRadius: 999,
    paddingHorizontal: 28,
    paddingVertical: 12,
  },
  copyButtonText: {
    fontFamily: fonts.bold,
    fontSize: 15,
    color: authColors.white,
  },
});
