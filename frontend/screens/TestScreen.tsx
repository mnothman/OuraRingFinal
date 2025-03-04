import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Button, Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import * as Linking from 'expo-linking';
import Constants from 'expo-constants';

const TestScreen = ({ route, navigation }: { route: any; navigation: any }) => {
  const [tokenInfo, setTokenInfo] = useState<string>('Loading token info...');
  const [deviceInfo, setDeviceInfo] = useState<string>('Loading device info...');
  const [linkingInfo, setLinkingInfo] = useState<string>('Loading linking info...');
  
  useEffect(() => {
    console.log('TestScreen mounted');
    console.log('Route params:', route?.params);
    
    const loadTokenInfo = async () => {
      try {
        const token = await SecureStore.getItemAsync('oauth_token');
        const userId = await SecureStore.getItemAsync('user_id');
        
        setTokenInfo(`Token: ${token ? token.substring(0, 10) + '...' : 'Not found'}\n\nUser ID: ${userId || 'Not found'}`);
        
        console.log('Token loaded:', token ? `${token.substring(0, 10)}...` : 'Not found');
        console.log('User ID loaded:', userId || 'Not found');
      } catch (error) {
        console.error('Error loading token info:', error);
        setTokenInfo(`Error loading token: ${error instanceof Error ? error.message : String(error)}`);
      }
    };
    
    const loadDeviceInfo = () => {
      try {
        const info = {
          platform: Platform.OS,
          version: Platform.Version,
          isExpo: Constants.executionEnvironment === 'standalone' ? 'No (Standalone)' : 'Yes',
          expoVersion: Constants.expoVersion || 'N/A',
          appName: Constants.expoConfig?.name || 'N/A',
          appScheme: Constants.expoConfig?.scheme || 'N/A',
        };
        
        setDeviceInfo(JSON.stringify(info, null, 2));
      } catch (error) {
        console.error('Error loading device info:', error);
        setDeviceInfo(`Error: ${error instanceof Error ? error.message : String(error)}`);
      }
    };
    
    const loadLinkingInfo = async () => {
      try {
        const url = await Linking.getInitialURL();
        const canOpenUrl = url ? await Linking.canOpenURL(url) : false;
        const baseUrl = Linking.createURL('/');
        
        const info = {
          initialUrl: url || 'None',
          canOpenInitialUrl: canOpenUrl,
          baseUrl: baseUrl,
          createURLTest: Linking.createURL('/test'),
        };
        
        setLinkingInfo(JSON.stringify(info, null, 2));
      } catch (error) {
        console.error('Error loading linking info:', error);
        setLinkingInfo(`Error: ${error instanceof Error ? error.message : String(error)}`);
      }
    };
    
    loadTokenInfo();
    loadDeviceInfo();
    loadLinkingInfo();
  }, [route]);

  const goToRealtimeHeartRate = () => {
    console.log('Navigating to RealtimeHeartRate screen');
    navigation.navigate('RealtimeHeartRate');
  };
  
  const testDeepLink = async () => {
    try {
      const url = 'myapp://oauth-callback?token=test-token&user=test-user';
      console.log('Testing deep link:', url);
      const supported = await Linking.canOpenURL(url);
      
      if (supported) {
        console.log('URL is supported, opening...');
        await Linking.openURL(url);
      } else {
        console.log('URL is not supported');
        alert(`Cannot open URL: ${url}`);
      }
    } catch (error) {
      console.error('Error testing deep link:', error);
      alert(`Error: ${error instanceof Error ? error.message : String(error)}`);
    }
  };
  
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Test Screen - Login Successful!</Text>
      <View style={styles.buttonContainer}>
        <Button 
          title="Go to Realtime Heart Rate" 
          onPress={goToRealtimeHeartRate}
          color="#4CAF50"
        />
        <Button 
          title="Test Deep Link" 
          onPress={testDeepLink}
          color="#2196F3"
        />
      </View>
      <ScrollView style={styles.scrollView}>
        <Text style={styles.text}>Authentication completed successfully.</Text>
        <Text style={styles.debugTitle}>Authentication Info:</Text>
        <Text style={styles.debugText}>{tokenInfo}</Text>
        
        <Text style={styles.debugTitle}>Device Info:</Text>
        <Text style={styles.debugText}>{deviceInfo}</Text>
        
        <Text style={styles.debugTitle}>Linking Info:</Text>
        <Text style={styles.debugText}>{linkingInfo}</Text>
        
        <Text style={styles.debugTitle}>Route Params:</Text>
        <Text style={styles.debugText}>
          {route?.params ? JSON.stringify(route.params, null, 2) : 'No route params'}
        </Text>
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'flex-start',
    alignItems: 'center',
    backgroundColor: 'black',
    padding: 20,
  },
  title: {
    color: 'white',
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 20,
  },
  text: {
    color: 'white',
    fontSize: 18,
    marginBottom: 30,
  },
  buttonContainer: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    width: '100%',
    marginBottom: 10,
  },
  scrollView: {
    width: '100%',
    marginTop: 20,
  },
  debugTitle: {
    color: '#00ff00',
    fontSize: 16,
    fontWeight: 'bold',
    marginTop: 20,
    marginBottom: 10,
  },
  debugText: {
    color: '#cccccc',
    fontSize: 14,
    fontFamily: 'monospace',
    backgroundColor: '#222222',
    padding: 10,
    borderRadius: 5,
  }
});

export default TestScreen;