import React, { useEffect, useState } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import * as Linking from 'expo-linking';
import { Alert, Text, View, StyleSheet, Button, ActivityIndicator } from 'react-native';
import * as SecureStore from 'expo-secure-store';

import LoginScreen from './screens/LoginScreen';
import TestScreen from './screens/TestScreen';
import RealtimeHeartRateScreen from './screens/RealtimeHeartRateScreen';
// import DailyStressScreen from './screens/DailyStressScreen';
// import HeartRateScreen from './screens/HeartRateScreen';
// import StressBaselineScreen from './screens/StressBaselineScreen';

const Stack = createNativeStackNavigator();

const App = () => {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [initialRoute, setInitialRoute] = useState('Login');
  const [debugInfo, setDebugInfo] = useState('App initializing...');
  const [isLoading, setIsLoading] = useState(true);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [isProcessingDeepLink, setIsProcessingDeepLink] = useState(false);

  // Function to check login status
  const checkLoginStatus = async () => {
    try {
      setDebugInfo(prev => `${prev}\nChecking login status...`);
      const token = await SecureStore.getItemAsync('oauth_token');
      if (token) {
        console.log('Found existing token, user is logged in');
        setDebugInfo(prev => `${prev}\nFound existing token, user is logged in`);
        setIsLoggedIn(true);
        setInitialRoute('Test');
      } else {
        setDebugInfo(prev => `${prev}\nNo token found, user needs to log in`);
      }
      setIsLoading(false);
    } catch (error) {
      console.error('Error checking login status:', error);
      setDebugInfo(prev => `${prev}\nError checking login: ${error instanceof Error ? error.message : String(error)}`);
      setIsLoading(false);
    }
  };

  useEffect(() => {
    checkLoginStatus();

    // Handle deep linking
    const handleDeepLink = async (url: string) => {
      console.log('Deep link received in App.tsx:', url);
      setDebugInfo(prev => `${prev}\nDeep link received: ${url}`);
      setIsProcessingDeepLink(true);
      
      // Check if this is an OAuth callback
      if (url.includes('oauth-callback')) {
        try {
          console.log('URL identified as OAuth callback');
          // Parse the URL to get token and user
          let queryString = '';
          
          if (url.includes('?')) {
            // Standard URL with query params
            console.log('URL contains ? - parsing as standard URL');
            const parts = url.split('?');
            if (parts.length < 2) {
              console.log('Invalid URL format, no query parameters after ?');
              setDebugInfo(prev => `${prev}\nInvalid URL format, no query parameters`);
              setIsProcessingDeepLink(false);
              return;
            }
            queryString = parts[1];
          } else if (url.includes('/--/oauth-callback')) {
            // Expo deep link format
            console.log('URL contains /--/ - parsing as Expo deep link');
            const parts = url.split('/--/oauth-callback');
            if (parts.length >= 2) {
              console.log('Successfully split Expo URL');
              queryString = parts[1].startsWith('?') ? parts[1].substring(1) : parts[1];
            } else {
              console.log('Invalid Expo URL format after splitting');
              setDebugInfo(prev => `${prev}\nInvalid Expo URL format`);
              setIsProcessingDeepLink(false);
              return;
            }
          } else {
            // Try to extract from URL path
            console.log('URL does not contain ? or /--/ - attempting to extract from path');
            const urlObj = new URL(url);
            const pathParts = urlObj.pathname.split('/');
            for (let i = 0; i < pathParts.length; i++) {
              if (pathParts[i] === 'oauth-callback' && i + 1 < pathParts.length) {
                queryString = pathParts[i + 1];
                break;
              }
            }
            
            if (!queryString) {
              console.log('Could not extract query string from URL path');
              // Last resort - try the hash
              if (urlObj.hash && urlObj.hash.includes('token=')) {
                console.log('Attempting to extract from hash');
                queryString = urlObj.hash.startsWith('#') ? urlObj.hash.substring(1) : urlObj.hash;
              } else {
                console.log('No query string found in URL');
                setDebugInfo(prev => `${prev}\nCould not extract parameters from URL`);
                setIsProcessingDeepLink(false);
                return;
              }
            }
          }
          
          console.log('Extracted query string:', queryString);
          
          // Parse the query string
          const params = new URLSearchParams(queryString);
          const token = params.get('token');
          const user = params.get('user');
          
          console.log('OAuth callback parsed:', {
            token: token ? `${token.substring(0, 10)}...` : 'missing',
            user: user || 'missing'
          });
          
          setDebugInfo(prev => `${prev}\nParsed params: token=${token ? 'present' : 'missing'}, user=${user || 'missing'}`);
          
          if (token && user) {
            // Store the credentials
            await SecureStore.setItemAsync('oauth_token', token);
            await SecureStore.setItemAsync('user_id', user);
            console.log('Credentials stored successfully');
            setDebugInfo(prev => `${prev}\nCredentials stored successfully`);
            
            // Update login state
            setIsLoggedIn(true);
            
            // Show alert for debugging
            Alert.alert('Deep Link Received', `Token: ${token.substring(0, 10)}...\nUser: ${user}`);
            
            // Navigate to Test screen
            setInitialRoute('Test');
          } else {
            setDebugInfo(prev => `${prev}\nMissing token or user in callback`);
            Alert.alert('Error', 'Missing token or user in callback');
          }
        } catch (error) {
          console.error('Error handling deep link:', error);
          setDebugInfo(prev => `${prev}\nError handling deep link: ${error instanceof Error ? error.message : String(error)}`);
          Alert.alert('Error', `Failed to process deep link: ${error instanceof Error ? error.message : String(error)}`);
        } finally {
          setIsProcessingDeepLink(false);
        }
      } else {
        setIsProcessingDeepLink(false);
      }
    };

    // Check for initial URL
    Linking.getInitialURL().then(url => {
      if (url) {
        console.log('Initial URL detected:', url);
        setDebugInfo(prev => `${prev}\nInitial URL detected: ${url}`);
        handleDeepLink(url);
      } else {
        setDebugInfo(prev => `${prev}\nNo initial URL detected`);
      }
    }).catch(err => {
      console.error('Error getting initial URL:', err);
      setDebugInfo(prev => `${prev}\nError getting initial URL: ${err instanceof Error ? err.message : String(err)}`);
    });

    // Listen for URL events while the app is running
    const subscription = Linking.addEventListener('url', (event) => {
      console.log('URL event received:', event.url);
      setDebugInfo(prev => `${prev}\nURL event received: ${event.url}`);
      handleDeepLink(event.url);
    });

    // Set up a periodic check to verify we're still connected
    const connectionCheck = setInterval(() => {
      if (reconnectAttempts > 0) {
        console.log(`Connection check (attempts: ${reconnectAttempts})`);
        // If we've been disconnected, check login status again
        checkLoginStatus();
        setReconnectAttempts(prev => prev - 1);
      }
    }, 2000);

    return () => {
      subscription.remove();
      clearInterval(connectionCheck);
    };
  }, [reconnectAttempts]);

  // Handle reconnection attempts when connection is lost
  useEffect(() => {
    const handleAppStateChange = () => {
      console.log('App state changed, attempting reconnection');
      setReconnectAttempts(5); // Try reconnecting 5 times
    };

    // Add listeners for app state changes
    const subscription = Linking.addEventListener('url', () => {
      handleAppStateChange();
    });

    return () => {
      subscription.remove();
    };
  }, []);

  if (isLoading || isProcessingDeepLink) {
    return (
      <View style={styles.loadingContainer}>
        <Text style={styles.title}>
          {isProcessingDeepLink ? 'Processing Login...' : 'Loading...'}
        </Text>
        <ActivityIndicator size="large" color="#4CAF50" />
        <Text style={styles.subtitle}>
          {isProcessingDeepLink ? 'Please wait while we verify your login' : 'Starting app...'}
        </Text>
        <Text style={styles.debugText}>{debugInfo}</Text>
        {isProcessingDeepLink && (
          <View style={styles.buttonContainer}>
            <Button 
              title="Continue to App" 
              onPress={() => {
                setIsProcessingDeepLink(false);
                if (isLoggedIn) {
                  setInitialRoute('Test');
                }
              }}
            />
          </View>
        )}
      </View>
    );
  }

  return (
    <NavigationContainer>
      <Stack.Navigator initialRouteName={initialRoute}>
        <Stack.Screen 
          name="Login" 
          component={LoginScreen} 
          options={{ headerShown: false }}
        />
        <Stack.Screen 
          name="Test" 
          component={TestScreen} 
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

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
    backgroundColor: '#f5f5f5',
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 20,
    color: '#333',
  },
  subtitle: {
    fontSize: 16,
    marginTop: 20,
    marginBottom: 20,
    color: '#666',
    textAlign: 'center',
  },
  debugText: {
    marginTop: 30,
    padding: 10,
    backgroundColor: '#f0f0f0',
    borderRadius: 5,
    width: '100%',
    fontSize: 12,
    height: 200,
  },
  buttonContainer: {
    marginTop: 20,
    width: '80%',
  }
});

export default App;
