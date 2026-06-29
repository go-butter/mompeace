import { Pressable, StyleSheet, Text, View } from 'react-native';

import NextIcon from '@/assets/images/common/next.svg';
import PrevIcon from '@/assets/images/common/prev.svg';
import { authColors } from '@/components/auth/colors';
import { fonts, nanumSquareRound } from '@/constants/fonts';
import { FoodLogCalendarDay } from '@/lib/api-client';

const WEEKDAY_LABELS = ['일', '월', '화', '수', '목', '금', '토'];

function toDateStr(year: number, month: number, day: number) {
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

function buildMonthGrid(year: number, month: number): (number | null)[][] {
  const firstWeekday = new Date(year, month - 1, 1).getDay();
  const daysInMonth = new Date(year, month, 0).getDate();

  const cells: (number | null)[] = [
    ...Array(firstWeekday).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  while (cells.length % 7 !== 0) cells.push(null);

  const weeks: (number | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) {
    weeks.push(cells.slice(i, i + 7));
  }
  return weeks;
}

export default function Calendar({
  year,
  month,
  selectedDate,
  statusByDate,
  onSelectDate,
  onChangeMonth,
}: {
  year: number;
  month: number;
  selectedDate: string;
  statusByDate: Record<string, FoodLogCalendarDay['overall_status']>;
  onSelectDate: (date: string) => void;
  onChangeMonth: (year: number, month: number) => void;
}) {
  const weeks = buildMonthGrid(year, month);

  const goToPrevMonth = () => {
    if (month === 1) onChangeMonth(year - 1, 12);
    else onChangeMonth(year, month - 1);
  };

  const goToNextMonth = () => {
    if (month === 12) onChangeMonth(year + 1, 1);
    else onChangeMonth(year, month + 1);
  };

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Pressable onPress={goToPrevMonth} hitSlop={8} style={styles.navButton}>
          <PrevIcon width={14} height={14} />
        </Pressable>
        <Text style={styles.monthLabel}>
          {year}년 {month}월
        </Text>
        <Pressable onPress={goToNextMonth} hitSlop={8} style={styles.navButton}>
          <NextIcon width={14} height={14} />
        </Pressable>
      </View>

      <View style={styles.weekdayRow}>
        {WEEKDAY_LABELS.map((label) => (
          <Text key={label} style={styles.weekdayLabel}>
            {label}
          </Text>
        ))}
      </View>

      {weeks.map((week, weekIndex) => (
        <View key={weekIndex} style={styles.weekRow}>
          {week.map((day, dayIndex) => {
            if (day == null) {
              return <View key={dayIndex} style={styles.dayCell} />;
            }
            const dateStr = toDateStr(year, month, day);
            const isSelected = dateStr === selectedDate;
            const status = statusByDate[dateStr];
            return (
              <Pressable
                key={dayIndex}
                style={styles.dayCell}
                onPress={() => onSelectDate(dateStr)}>
                <View style={[styles.dayCircle, isSelected && styles.dayCircleSelected]}>
                  <Text style={[styles.dayText, isSelected && styles.dayTextSelected]}>{day}</Text>
                </View>
                <View style={[styles.dot, status ? styles.dotFilled : styles.dotHidden]} />
              </Pressable>
            );
          })}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: authColors.white,
    borderRadius: 25,
    padding: 18,
    shadowColor: '#FFEEF0',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 12,
    elevation: 4,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
    marginBottom: 12,
  },
  navButton: {
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  monthLabel: {
    fontFamily: nanumSquareRound.bold,
    fontSize: 16,
    color: authColors.brown,
    minWidth: 90,
    textAlign: 'center',
  },
  weekdayRow: {
    flexDirection: 'row',
  },
  weekdayLabel: {
    flex: 1,
    textAlign: 'center',
    fontFamily: fonts.regular,
    fontSize: 11,
    color: authColors.gray,
    marginBottom: 4,
  },
  weekRow: {
    flexDirection: 'row',
  },
  dayCell: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 4,
  },
  dayCircle: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dayCircleSelected: {
    backgroundColor: authColors.pink,
  },
  dayText: {
    fontFamily: fonts.medium,
    fontSize: 13,
    color: authColors.brown,
  },
  dayTextSelected: {
    color: authColors.white,
    fontFamily: fonts.semiBold,
  },
  dot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
    marginTop: 2,
  },
  dotFilled: {
    backgroundColor: authColors.gray,
  },
  dotHidden: {
    backgroundColor: 'transparent',
  },
});
