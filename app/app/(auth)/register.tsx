import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { authColors } from '@/components/auth/colors';
import { fonts } from '@/constants/fonts';
import { useAuth } from '@/context/auth-context';
import { ApiError, registerUser } from '@/lib/api-client';

function LabeledInput({
  label,
  placeholder,
  value,
  onChangeText,
  secureTextEntry,
  isPasswordVisible,
  onToggleVisibility,
  error,
}: {
  label: string;
  placeholder: string;
  value: string;
  onChangeText: (text: string) => void;
  secureTextEntry?: boolean;
  isPasswordVisible?: boolean;
  onToggleVisibility?: () => void;
  error?: string | null;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.inputWrapper}>
        <TextInput
          style={[styles.input, secureTextEntry && styles.passwordInput]}
          placeholder={placeholder}
          placeholderTextColor={authColors.gray}
          value={value}
          onChangeText={onChangeText}
          secureTextEntry={secureTextEntry && !isPasswordVisible}
          autoCapitalize="none"
        />
        {secureTextEntry && (
          <Pressable style={styles.eyeButton} onPress={onToggleVisibility} hitSlop={8}>
            <Ionicons
              name={isPasswordVisible ? 'eye-off-outline' : 'eye-outline'}
              size={20}
              color={authColors.gray}
            />
          </Pressable>
        )}
      </View>
      {error && <Text style={styles.errorText}>{error}</Text>}
    </View>
  );
}

export default function RegisterScreen() {
  const { login } = useAuth();
  const [nickname, setNickname] = useState('');
  const [id, setId] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [idError, setIdError] = useState<string | null>(null);
  const [confirmPasswordError, setConfirmPasswordError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [confirmPasswordVisible, setConfirmPasswordVisible] = useState(false);
  const isMountedRef = useRef(true);

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const handlePasswordChange = (text: string) => {
    setPassword(text);
    setConfirmPasswordError(null);
  };

  const handleConfirmPasswordChange = (text: string) => {
    setConfirmPassword(text);
    setConfirmPasswordError(null);
  };

  const handleRegister = async () => {
    setIdError(null);
    setConfirmPasswordError(null);

    if (!nickname.trim() || !id.trim() || !password.trim() || !confirmPassword.trim()) {
      setIdError('모든 항목을 입력해 주세요.');
      return;
    }

    if (password !== confirmPassword) {
      setConfirmPasswordError('비밀번호가 일치하지 않습니다.');
      return;
    }

    setLoading(true);
    try {
      const response = await registerUser({
        nickname,
        login_id: id,
        password,
        password_confirm: confirmPassword,
      });
      login({
        user_id: response.user_id,
        nickname: response.nickname,
        login_id: response.login_id,
        pregnancy_week: null,
        due_date: null,
        allergy_info: null,
      });
      if (!isMountedRef.current) return;
      router.push('/(auth)/input');
    } catch (err) {
      if (!isMountedRef.current) return;
      if (err instanceof ApiError) {
        setIdError(err.message);
      } else {
        setIdError((err as Error).message);
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Ionicons name="chevron-back" size={24} color={authColors.brown} />
        </Pressable>
        <Text style={styles.headerTitle}>회원가입</Text>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <LabeledInput
          label="닉네임*"
          placeholder="Enter your nickname"
          value={nickname}
          onChangeText={setNickname}
        />
        <LabeledInput
          label="아이디*"
          placeholder="Enter your id"
          value={id}
          onChangeText={setId}
          error={idError}
        />
        <LabeledInput
          label="비밀번호*"
          placeholder="Enter your password"
          value={password}
          onChangeText={handlePasswordChange}
          secureTextEntry
          isPasswordVisible={passwordVisible}
          onToggleVisibility={() => setPasswordVisible((prev) => !prev)}
        />
        <LabeledInput
          label="비밀번호 확인*"
          placeholder="Confirm password"
          value={confirmPassword}
          onChangeText={handleConfirmPasswordChange}
          secureTextEntry
          isPasswordVisible={confirmPasswordVisible}
          onToggleVisibility={() => setConfirmPasswordVisible((prev) => !prev)}
          error={confirmPasswordError}
        />

        <Pressable
          style={[styles.registerButton, loading && styles.buttonDisabled]}
          onPress={handleRegister}
          disabled={loading}>
          <View style={styles.buttonContent}>
            {loading && <ActivityIndicator size="small" color={authColors.white} />}
            <Text style={styles.registerButtonText}>{loading ? '등록 중...' : '등록'}</Text>
          </View>
        </Pressable>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: authColors.white,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
    paddingHorizontal: 24,
    paddingTop: 60,
    paddingBottom: 16,
  },
  headerTitle: {
    fontSize: 20,
    fontFamily: fonts.semiBold,
    color: authColors.brown,
  },
  content: {
    paddingHorizontal: 24,
    paddingTop: 12,
    paddingBottom: 40,
  },
  field: {
    marginBottom: 20,
  },
  label: {
    fontSize: 14,
    fontFamily: fonts.medium,
    color: authColors.brown,
    marginBottom: 8,
  },
  inputWrapper: {
    position: 'relative',
  },
  input: {
    borderWidth: 1,
    borderColor: authColors.border,
    backgroundColor: authColors.white,
    borderRadius: 999,
    paddingHorizontal: 20,
    paddingVertical: 14,
    fontSize: 15,
    fontFamily: fonts.regular,
  },
  passwordInput: {
    paddingRight: 48,
  },
  eyeButton: {
    position: 'absolute',
    right: 16,
    top: 0,
    bottom: 0,
    justifyContent: 'center',
    alignItems: 'center',
  },
  registerButton: {
    backgroundColor: authColors.pink,
    borderRadius: 999,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 16,
  },
  buttonContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  registerButtonText: {
    color: authColors.white,
    fontSize: 17,
    fontFamily: fonts.bold,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  errorText: {
    color: authColors.pink,
    fontSize: 13,
    fontFamily: fonts.regular,
    marginTop: 6,
  },
});
