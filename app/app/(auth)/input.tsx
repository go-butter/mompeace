import { Ionicons } from '@expo/vector-icons';
import DateTimePicker from '@react-native-community/datetimepicker';
import { router } from 'expo-router';
import { useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import BabyIcon from '@/assets/images/onboarding/baby.svg';
import CalIcon from '@/assets/images/onboarding/cal.svg';
import InformationIcon from '@/assets/images/onboarding/information.svg';
import { authColors } from '@/components/auth/colors';
import { GradientBackground } from '@/components/auth/gradient-background';
import { fonts } from '@/constants/fonts';

function formatDate(date: Date) {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  return `${yyyy}.${mm}.${dd}.`;
}

export default function PregnancyInputScreen() {
  const [week, setWeek] = useState('21');
  const [day, setDay] = useState('3');
  const [dueDate, setDueDate] = useState(new Date(2026, 9, 26));
  const [showDatePicker, setShowDatePicker] = useState(false);

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
          <Text style={{ color: authColors.pink }}>기본 정보</Text>
          <Text style={{ color: authColors.brown }}>를{'\n'}입력해 주세요</Text>
        </Text>
        <Text style={styles.subtitle}>
          정확한 정보를 입력할수록{'\n'}더 맘편한 추천을 받을 수 있어요
        </Text>

        <View style={styles.card}>
          <View style={styles.row}>
            <View style={styles.iconCircle}>
              <BabyIcon width={24} height={24} />
            </View>
            <Text style={styles.rowTitle}>임신 주차</Text>
          </View>
          <View style={styles.weekInputs}>
            <View style={styles.weekField}>
              <TextInput
                style={styles.numberInput}
                value={week}
                onChangeText={setWeek}
                keyboardType="number-pad"
                maxLength={2}
              />
              <Text style={styles.weekLabel}>주차</Text>
            </View>
            <View style={styles.weekField}>
              <TextInput
                style={styles.numberInput}
                value={day}
                onChangeText={setDay}
                keyboardType="number-pad"
                maxLength={1}
              />
              <Text style={styles.weekLabel}>일</Text>
            </View>
          </View>

          <View style={styles.divider} />

          <View style={styles.row}>
            <View style={styles.iconCircle}>
              <CalIcon width={24} height={24} />
            </View>
            <Text style={styles.rowTitle}>출산 예정일</Text>
          </View>
          <Pressable style={styles.dateField} onPress={() => setShowDatePicker(true)}>
            <Text style={styles.dateInput}>{formatDate(dueDate)}</Text>
            <Ionicons name="calendar-outline" size={20} color={authColors.pink} />
          </Pressable>
          {showDatePicker && (
            <DateTimePicker
              value={dueDate}
              mode="date"
              display="default"
              onChange={(_event, selectedDate) => {
                setShowDatePicker(false);
                if (selectedDate) {
                  setDueDate(selectedDate);
                }
              }}
            />
          )}

          <View style={styles.banner}>
            <InformationIcon width={18} height={18} />
            <Text style={styles.bannerText}>정확한 정보일수록 더 맘편한 추천을 받을 수 있어요</Text>
          </View>
        </View>
      </ScrollView>

      <View style={styles.footer}>
        <Pressable style={styles.nextButton} onPress={() => router.push('/(tabs)/home')}>
          <Text style={styles.nextButtonText}>다음</Text>
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
    paddingTop: 60,
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
  card: {
    backgroundColor: authColors.white,
    borderRadius: 24,
    padding: 20,
    marginTop: 28,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  iconCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#FFF0F0',
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowTitle: {
    fontSize: 16,
    fontFamily: fonts.medium,
    color: authColors.brown,
  },
  weekInputs: {
    flexDirection: 'row',
    gap: 16,
    marginTop: 16,
  },
  weekField: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  numberInput: {
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 10,
    fontSize: 15,
    fontFamily: fonts.regular,
    width: 64,
    textAlign: 'center',
  },
  weekLabel: {
    fontSize: 14,
    fontFamily: fonts.regular,
    color: authColors.gray,
  },
  divider: {
    height: 1,
    backgroundColor: authColors.border,
    marginVertical: 20,
  },
  dateField: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1,
    borderColor: authColors.border,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 10,
    marginTop: 16,
  },
  dateInput: {
    fontSize: 15,
    fontFamily: fonts.regular,
    flex: 1,
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
  footer: {
    paddingHorizontal: 24,
    paddingBottom: 32,
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
});
