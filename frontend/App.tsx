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

const prefix = Linking.createURL('/');

const App = () => {
  const linking = {
    prefixes: [prefix],
    config: {
      screens: {
        Login: 'login',
        // Home: 'home',
        RealtimeHeartRate: 'realtime-heart-rate',
        // DailyStress: 'daily-stress',
        // HeartRate: 'heart-rate',
        // StressBaseline: 'stress-baseline',
      },
    },
  };

  return (
    <NavigationContainer linking={linking}>
      <Stack.Navigator initialRouteName="Login">
        <Stack.Screen name="Login" component={LoginScreen} />
        {/* <Stack.Screen name="Home" component={HomeScreen} /> */}
        <Stack.Screen name="RealtimeHeartRate" component={RealtimeHeartRateScreen} />
        {/* <Stack.Screen name="DailyStress" component={DailyStressScreen} /> */}
        {/* <Stack.Screen name="HeartRate" component={HeartRateScreen} /> */}
        {/* <Stack.Screen name="StressBaseline" component={StressBaselineScreen} /> */}
      </Stack.Navigator>
    </NavigationContainer>
  );
};

export default App; 