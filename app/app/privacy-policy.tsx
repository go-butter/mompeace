import { router } from 'expo-router';
import { ScrollView, StyleSheet, Text, View, Pressable } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import PrevIcon from '@/assets/images/common/prev.svg';
import { authColors } from '@/components/auth/colors';
import { fonts } from '@/constants/fonts';

const PRIVACY_POLICY_SECTIONS: { heading: string; body: string }[] = [
  {
    heading: '',
    body: '맘편하게(이하 "서비스")는 이용자의 개인정보를 소중히 여기며, 「개인정보 보호법」 등 관련 법령을 준수합니다. 본 방침은 서비스가 어떤 정보를 수집하고 어떻게 이용·보관·파기하는지 안내합니다.\n\n본 서비스는 대학 경진대회 출품을 위한 데모 애플리케이션으로, 실제 상용 서비스가 아닙니다.',
  },
  {
    heading: '1. 수집하는 개인정보 항목',
    body: '서비스는 다음 정보를 수집합니다.\n\n[회원가입 시]\n• 닉네임, 비밀번호\n\n[서비스 이용 시]\n• 출산예정일 (임신 주차 계산 목적)\n• 관심 영양소 선택 정보\n• 식사 기록 (음식명, 섭취량, 섭취 시각)\n• 수분 섭취 기록\n• 영양성분표 촬영 이미지 (OCR 인식 목적)\n\n[자동 생성 정보]\n• 개인별 판정 민감도 보정값\n• 서비스 이용 기록',
  },
  {
    heading: '2. 민감정보의 처리',
    body: '임신 여부, 출산예정일, 식사 기록은 「개인정보 보호법」상 건강에 관한 정보로서 민감정보에 해당합니다. 서비스는 이용자가 별도로 동의한 경우에 한하여 해당 정보를 처리하며, 영양 안전 판정 목적 외의 용도로 이용하지 않습니다.',
  },
  {
    heading: '3. 개인정보의 이용 목적',
    body: '수집한 정보는 다음 목적으로만 이용합니다.\n\n• 회원 식별 및 로그인\n• 임신 주차에 맞는 영양 기준 적용\n• 섭취 영양소 누적 및 안전 여부 판정\n• 음식 추천 및 건강 리포트 제공\n• 영양성분표 이미지에서 수치 추출',
  },
  {
    heading: '4. 보유 및 이용 기간',
    body: '원칙적으로 회원 탈퇴 시 지체 없이 파기합니다.\n\n• 회원 정보: 탈퇴 시까지\n• 식사·수분 기록: 탈퇴 시까지\n• 촬영 이미지: 수치 추출 완료 후 즉시 삭제\n\n관계 법령에 따라 보존이 필요한 경우 해당 기간 동안 보관합니다.',
  },
  {
    heading: '5. 개인정보의 파기',
    body: '보유 기간이 지나거나 처리 목적이 달성되면 지체 없이 파기합니다. 전자적 파일은 복구할 수 없는 방법으로 삭제하며, 출력물은 분쇄하거나 소각합니다.',
  },
  {
    heading: '6. 제3자 제공',
    body: '서비스는 이용자의 개인정보를 제3자에게 제공하지 않습니다. 다만 법령에 따라 요구되는 경우는 예외로 합니다.',
  },
  {
    heading: '7. 처리 위탁',
    body: '영양성분표 이미지의 수치 추출을 위해 외부 AI 처리 서비스(Google Gemini)를 이용합니다. 위탁 범위는 이미지에서 숫자를 읽어내는 작업에 한정되며, 안전 여부 판정은 서비스 내부 규칙 엔진이 수행합니다.\n\n촬영 이미지는 수치 추출 목적 외에 저장·활용되지 않습니다.',
  },
  {
    heading: '8. 이용자의 권리',
    body: '이용자는 언제든지 다음 권리를 행사할 수 있습니다.\n\n• 개인정보 열람 요구\n• 오류 정정 요구\n• 삭제 요구\n• 처리 정지 요구\n\n마이페이지에서 직접 정보를 수정하거나 회원 탈퇴를 통해 삭제할 수 있습니다.',
  },
  {
    heading: '9. 개인정보의 안전성 확보 조치',
    body: '• 비밀번호는 암호화하여 저장합니다.\n• 개인정보에 접근할 수 있는 인원을 최소한으로 제한합니다.\n• 이용자별로 데이터를 분리하여 다른 이용자의 정보에 접근할 수 없도록 합니다.',
  },
  {
    heading: '10. 만 14세 미만 아동',
    body: '서비스는 만 14세 미만 아동의 개인정보를 수집하지 않습니다.',
  },
  {
    heading: '11. 의료 서비스가 아님',
    body: '서비스가 제공하는 영양 정보는 공식 영양섭취기준(KDRI)과 국내외 가이드라인에 근거한 참고 자료이며, 의학적 진단이나 처방을 대체하지 않습니다. 건강에 관한 판단은 반드시 의료 전문가와 상담하시기 바랍니다.',
  },
  {
    heading: '12. 개인정보 보호책임자',
    body: '개인정보 처리에 관한 문의는 아래로 연락해 주시기 바랍니다.\n\n• 팀명: 고버터\n• 문의: 마이페이지 > 문의하기\n\n본 서비스는 데모 애플리케이션으로, 실제 고객 응대 체계를 운영하지 않습니다.',
  },
  {
    heading: '13. 방침의 변경',
    body: '본 방침은 2026년 8월 12일부터 적용됩니다. 내용이 변경되는 경우 서비스 내 공지를 통해 안내합니다.',
  },
];

export default function PrivacyPolicyScreen() {
  const insets = useSafeAreaInsets();

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 7, paddingBottom: insets.bottom + 32 }]}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.prevButton} hitSlop={8}>
          <PrevIcon width={15} height={15} />
        </Pressable>
        <Text style={styles.title}>개인정보 처리방침</Text>
      </View>

      <View style={styles.card}>
        {PRIVACY_POLICY_SECTIONS.map((section, index) => (
          <View key={index} style={index > 0 ? styles.section : undefined}>
            {section.heading !== '' && <Text style={styles.heading}>{section.heading}</Text>}
            <Text style={styles.body}>{section.body}</Text>
          </View>
        ))}
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
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  prevButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: authColors.pinkLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontFamily: fonts.semiBold,
    fontSize: 20,
    color: authColors.brown,
  },
  card: {
    marginTop: 20,
    backgroundColor: authColors.white,
    borderRadius: 15,
    borderWidth: 1,
    borderColor: authColors.border,
    padding: 20,
  },
  section: {
    marginTop: 20,
  },
  heading: {
    fontFamily: fonts.semiBold,
    fontSize: 15,
    color: authColors.brown,
    marginBottom: 8,
  },
  body: {
    fontFamily: fonts.regular,
    fontSize: 14,
    lineHeight: 21,
    color: authColors.grayDark,
  },
});
