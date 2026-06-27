import { createContext, ReactNode, useContext, useEffect, useState } from 'react';

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
  const [intake, setIntake] = useState<IntakeTodayResponse | null>(null);
  const [foodLog, setFoodLog] = useState<FoodLogEntry[]>([]);
  const [allFoodLog, setAllFoodLog] = useState<FoodLogEntry[]>([]);
  const [hasEntries, setHasEntries] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    if (!user?.user_id) return;
    setLoading(true);
    setError(null);

    try {
      const [intakeRes, foodLogRes] = await Promise.all([
        getIntakeToday(user.user_id),
        getFoodLogToday(user.user_id),
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
  };

  useEffect(() => {
    if (!user?.user_id) return;
    refresh();
  }, [user?.user_id]);

  return (
    <IntakeContext.Provider
      value={{ intake, foodLog, allFoodLog, hasEntries, loading, error, refresh }}>
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
