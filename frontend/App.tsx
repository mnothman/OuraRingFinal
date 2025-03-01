import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import * as Linking from 'expo-linking';

import LoginScreen from './screens/LoginScreen';
// import HomeScreen from './screens/HomeScreen';
import RealtimeHeartRateScreen from './screens/RealtimeHeartRateScreen';
// import DailyStressScreen from './screens/DailyStressScreen';
// import HeartRateScreen from './screens/HeartRateScreen';
// import StressBaselineScreen from './screens/StressBaselineScreen';

const Stack = createNativeStackNavigator();

// Use Expo scheme instead of ngrok
const prefix = 'myapp://';
console.log('Deep linking prefix:', prefix); // Debug log

const App = () => {
  const linking = {
    prefixes: [prefix],
    config: {
      screens: {
        Login: 'login',
        // Home: 'home',
        RealtimeHeartRate: 'realtimehr',
        OAuthCallback: {
          path: 'oauth-callback',
          parse: {
            token: (token: string) => token,
            user: (user: string) => user,
          }
        },
        // DailyStress: 'daily-stress',
        // HeartRate: 'heart-rate',
        // StressBaseline: 'stress-baseline',
      },
    },
  };

  return (
    <NavigationContainer linking={linking}>
      <Stack.Navigator initialRouteName="Login">
        <Stack.Screen 
          name="Login" 
          component={LoginScreen} 
          options={{ headerShown: false }}
        />
        {/* <Stack.Screen name="Home" component={HomeScreen} /> */}
        <Stack.Screen 
          name="RealtimeHeartRate" 
          component={RealtimeHeartRateScreen}
          options={{ headerShown: true }}
        />
        {/* <Stack.Screen name="DailyStress" component={DailyStressScreen} /> */}
        {/* <Stack.Screen name="HeartRate" component={HeartRateScreen} /> */}
        {/* <Stack.Screen name="StressBaseline" component={StressBaselineScreen} /> */}
      </Stack.Navigator>
    </NavigationContainer>
  );
};

export default App; 