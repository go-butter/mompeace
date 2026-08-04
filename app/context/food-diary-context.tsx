import { useCallback, useEffect, useState } from 'react';

import { useAuth } from '@/context/auth-context';
import {
  ApiError,
  FoodLogCalendarDay,
  FoodLogEntry,
  getFoodLogByDate,
  getFoodLogCalendar,
  getIntakeSummary,
  IntakeSummaryResponse,
} from '@/lib/api-client';

function todayIso() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

export function useFoodDiary() {
  const { user } = useAuth();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [selectedDate, setSelectedDate] = useState(todayIso());

  const [statusByDate, setStatusByDate] = useState<
    Record<string, FoodLogCalendarDay['overall_status']>
  >({});
  const [summary, setSummary] = useState<IntakeSummaryResponse | null>(null);
  const [foodLog, setFoodLog] = useState<FoodLogEntry[]>([]);

  const [loadingCalendar, setLoadingCalendar] = useState(true);
  const [loadingDay, setLoadingDay] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user?.user_id) return;
    setLoadingCalendar(true);
    getFoodLogCalendar(user.user_id, year, month)
      .then((res) => {
        const map: Record<string, FoodLogCalendarDay['overall_status']> = {};
        res.days.forEach((d) => {
          map[d.date] = d.overall_status;
        });
        setStatusByDate(map);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : (err as Error).message))
      .finally(() => setLoadingCalendar(false));
  }, [user?.user_id, year, month]);

  const refreshDay = useCallback(() => {
    if (!user?.user_id) return Promise.resolve();
    setLoadingDay(true);
    setError(null);
    return Promise.all([
      getIntakeSummary(user.user_id, selectedDate),
      getFoodLogByDate(user.user_id, selectedDate),
    ])
      .then(([summaryRes, foodLogRes]) => {
        setSummary(summaryRes);
        setFoodLog(foodLogRes.logs);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : (err as Error).message))
      .finally(() => setLoadingDay(false));
  }, [user?.user_id, selectedDate]);

  useEffect(() => {
    refreshDay();
  }, [refreshDay]);

  const changeMonth = (newYear: number, newMonth: number) => {
    setYear(newYear);
    setMonth(newMonth);
  };

  return {
    year,
    month,
    selectedDate,
    setSelectedDate,
    changeMonth,
    statusByDate,
    summary,
    foodLog,
    loading: loadingCalendar || loadingDay,
    error,
    isToday: selectedDate === todayIso(),
    refreshDay,
  };
}
