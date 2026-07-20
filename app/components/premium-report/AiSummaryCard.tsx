import { StyleSheet, Text, View } from 'react-native';

import { authColors } from '@/components/auth/colors';
import { fonts } from '@/constants/fonts';
import type { PremiumReportAiSummary } from '@/lib/api-client';

interface AiSummaryCardProps {
  summary: PremiumReportAiSummary;
}

export default function AiSummaryCard({ summary }: AiSummaryCardProps) {
  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.sparkle}>✨</Text>
        <Text style={styles.title}>{summary.title}</Text>
      </View>
      <View style={styles.divider} />
      <Text style={styles.intro}>AI가 분석한 결과,</Text>
      {summary.messages.map((message, index) => (
        <View key={index} style={styles.messageRow}>
          <Text style={styles.bullet}>•</Text>
          <Text style={styles.messageText}>{message}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FEF6F6',
    borderRadius: 20,
    padding: 18,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  sparkle: {
    fontSize: 15,
  },
  title: {
    fontFamily: fonts.semiBold,
    fontSize: 15,
    color: authColors.brown,
  },
  divider: {
    height: 1,
    backgroundColor: authColors.border,
    marginTop: 10,
    marginBottom: 10,
  },
  intro: {
    fontFamily: fonts.medium,
    fontSize: 13,
    color: authColors.brown,
    marginBottom: 6,
  },
  messageRow: {
    flexDirection: 'row',
    gap: 6,
    marginTop: 4,
  },
  bullet: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.gray,
  },
  messageText: {
    flex: 1,
    fontFamily: fonts.regular,
    fontSize: 13,
    color: authColors.brown,
    lineHeight: 20,
  },
});
