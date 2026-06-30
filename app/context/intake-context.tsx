import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { useAuth } from '@/context/auth-context';
import {
  ApiError,
  FoodLogEntry,
  getFoodLogToday,
  getIntakeToday,
  IntakeTodayResponse,
} from '@/lib/api-client';

interface IntakeContextValue {
  intake: IntakeTodayResponse | null;
  foodLog: FoodLogEntry[];
  allFoodLog: FoodLogEntry[];
  hasEntries: boolean;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const IntakeContext = createContext<IntakeContextValue | null>(null);

export function IntakeProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const userId = user?.user_id;
  const [intake, setIntake] = useState<IntakeTodayResponse | null>(null);
  const [foodLog, setFoodLog] = useState<FoodLogEntry[]>([]);
  const [allFoodLog, setAllFoodLog] = useState<FoodLogEntry[]>([]);
  const [hasEntries, setHasEntries] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    setError(null);

    try {
      const [intakeRes, foodLogRes] = await Promise.all([
        getIntakeToday(userId),
        getFoodLogToday(userId),
      ]);
      setIntake(intakeRes);
      setHasEntries(foodLogRes.count > 0);
      setFoodLog(foodLogRes.logs.slice(-3));
      setAllFoodLog(foodLogRes.logs);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const value = useMemo(
    () => ({ intake, foodLog, allFoodLog, hasEntries, loading, error, refresh }),
    [intake, foodLog, allFoodLog, hasEntries, loading, error, refresh]
  );

  return (
    <IntakeContext.Provider value={value}>
      {children}
    </IntakeContext.Provider>
  );
}

export function useIntake() {
  const context = useContext(IntakeContext);
  if (!context) {
    throw new Error('useIntake must be used within an IntakeProvider');
  }
  return context;
}
