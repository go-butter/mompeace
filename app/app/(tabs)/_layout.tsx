import { Tabs } from 'expo-router';
import React from 'react';
import { Text } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import HomeIcon from '@/assets/images/common/tab_clarity_home-line.svg';
import BarcodeIcon from '@/assets/images/common/tab_barcode.svg';
import PlantIcon from '@/assets/images/common/tab_tabler_plant.svg';
import PersonIcon from '@/assets/images/common/tab_charm_person.svg';
import { HapticTab } from '@/components/haptic-tab';

const ACTIVE_COLOR = '#F47E8A';
const INACTIVE_COLOR = '#848484';

function TabLabel({ focused, label }: { focused: boolean; label: string }) {
  return (
    <Text
      style={{
        color: focused ? ACTIVE_COLOR : INACTIVE_COLOR,
        fontWeight: focused ? 'bold' : 'normal',
        fontSize: 11,
        marginTop: 4,
      }}>
      {label}
    </Text>
  );
}

const CONTENT_HEIGHT = 80;

export default function TabLayout() {
  const insets = useSafeAreaInsets();

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarButton: HapticTab,
        tabBarStyle: {
          backgroundColor: '#fff',
          borderTopLeftRadius: 15,
          borderTopRightRadius: 15,
          // react-navigation applies paddingBottom: insets.bottom inside this height,
          // so add the inset on top to keep the visual content area at CONTENT_HEIGHT.
          height: CONTENT_HEIGHT + insets.bottom,
          shadowColor: '#000',
          shadowOffset: { width: 0, height: 0 },
          shadowOpacity: 0.25,
          shadowRadius: 4,
          elevation: 4,
        },
        tabBarItemStyle: {
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        },
        tabBarIconStyle: {
          marginTop: 12,
        },
      }}>
      <Tabs.Screen
        name="home"
        options={{
          tabBarLabel: ({ focused }) => <TabLabel focused={focused} label="홈" />,
          tabBarIcon: ({ focused }) => (
            <HomeIcon width={28} height={28} color={focused ? ACTIVE_COLOR : INACTIVE_COLOR} />
          ),
        }}
      />
      <Tabs.Screen
        name="scan"
        options={{
          tabBarLabel: ({ focused }) => <TabLabel focused={focused} label="스캔" />,
          tabBarIcon: ({ focused }) => (
            <BarcodeIcon width={26} height={26} color={focused ? ACTIVE_COLOR : INACTIVE_COLOR} />
          ),
        }}
      />
      <Tabs.Screen
        name="recommend"
        options={{
          tabBarLabel: ({ focused }) => <TabLabel focused={focused} label="추천" />,
          tabBarIcon: ({ focused }) => (
            <PlantIcon width={27} height={28} color={focused ? ACTIVE_COLOR : INACTIVE_COLOR} />
          ),
        }}
      />
      <Tabs.Screen
        name="mypage"
        options={{
          tabBarLabel: ({ focused }) => <TabLabel focused={focused} label="마이페이지" />,
          tabBarIcon: ({ focused }) => (
            <PersonIcon width={29} height={29} color={focused ? ACTIVE_COLOR : INACTIVE_COLOR} />
          ),
        }}
      />
    </Tabs>
  );
}
