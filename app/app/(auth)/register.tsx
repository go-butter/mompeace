import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { authColors } from '@/components/auth/colors';
import { fonts } from '@/constants/fonts';

function LabeledInput({
  label,
  placeholder,
  value,
  onChangeText,
  secureTextEntry,
}: {
  label: string;
  placeholder: string;
  value: string;
  onChangeText: (text: string) => void;
  secureTextEntry?: boolean;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        style={styles.input}
        placeholder={placeholder}
        placeholderTextColor={authColors.gray}
        value={value}
        onChangeText={onChangeText}
        secureTextEntry={secureTextEntry}
        autoCapitalize="none"
      />
    </View>
  );
}

export default function RegisterScreen() {
  const [nickname, setNickname] = useState('');
  const [id, setId] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

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
        <LabeledInput label="아이디*" placeholder="Enter your id" value={id} onChangeText={setId} />
        <LabeledInput
          label="비밀번호*"
          placeholder="Enter your password"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
        />
        <LabeledInput
          label="비밀번호 확인*"
          placeholder="Confirm password"
          value={confirmPassword}
          onChangeText={setConfirmPassword}
          secureTextEntry
        />

        <Pressable style={styles.registerButton} onPress={() => router.push('/(auth)/input')}>
          <Text style={styles.registerButtonText}>등록</Text>
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
  registerButton: {
    backgroundColor: authColors.pink,
    borderRadius: 999,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 16,
  },
  registerButtonText: {
    color: authColors.white,
    fontSize: 17,
    fontFamily: fonts.bold,
  },
});
