import React, { useState, useEffect } from 'react';
import { View, Button, StyleSheet, Alert, Text, TextInput, ScrollView, TouchableOpacity } from 'react-native';
import * as Linking from 'expo-linking';
import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';

// Get the backend URL from environment or use the ngrok URL
const BACKEND_URL = Constants.expoConfig?.extra?.backendUrl || 'https://d03b-2601-207-380-fb60-9996-b006-c610-fbd5.ngrok-free.app';

const LoginScreen = ({ navigation }: { navigation: any }) => {
  const [debugInfo, setDebugInfo] = useState<string>('Waiting for login...');
  const [manualToken, setManualToken] = useState<string>('');
  const [manualUser, setManualUser] = useState<string>('');
  const [showWarning, setShowWarning] = useState<boolean>(false);

  useEffect(() => {
    // Add URL listener for handling deep links
    const handleUrl = async ({ url }: { url: string }) => {
      console.log('Received URL in LoginScreen:', url);
      setDebugInfo(prev => `${prev}\nReceived URL: ${url}`);

      try {
        // Parse the URL to get the token and user
        const parsedUrl = Linking.parse(url);
        console.log('Parsed URL:', parsedUrl);
        
        if (parsedUrl.queryParams?.token && parsedUrl.queryParams?.user) {
          const { token, user } = parsedUrl.queryParams;
          
          // Store credentials
          await SecureStore.setItemAsync('oauth_token', token.toString());
          await SecureStore.setItemAsync('user_id', user.toString());
          
          console.log('Credentials stored, navigating to Test screen...');
          setDebugInfo(prev => `${prev}\nCredentials stored, navigating...`);
          
          // Navigate to test screen
          navigation.reset({
            index: 0,
            routes: [{ name: 'Test' }],
          });
        }
      } catch (error) {
        console.error('Error handling deep link:', error);
        setDebugInfo(prev => `${prev}\nDeep link error: ${error instanceof Error ? error.message : String(error)}`);
      }
    };

    // Set up URL listeners
    const subscription = Linking.addEventListener('url', handleUrl);

    // Check for initial URL (in case app was opened with URL)
    Linking.getInitialURL().then(url => {
      if (url) {
        handleUrl({ url });
      }
    });

    // Log some debug info on mount
    const logDebugInfo = async () => {
      try {
        const initialUrl = await Linking.getInitialURL();
        const baseUrl = Linking.createURL('/');
        
        setDebugInfo(prev => 
          `${prev}\n\nDevice Info:` +
          `\n- Platform: ${Constants.platform?.os || 'unknown'}` +
          `\n- Backend URL: ${BACKEND_URL}` +
          `\n- Initial URL: ${initialUrl || 'none'}` +
          `\n- Base URL: ${baseUrl}`
        );
        
        // Check if we can open the login URL
        const loginUrl = `${BACKEND_URL}/auth/login`;
        const canOpen = await Linking.canOpenURL(loginUrl);
        setDebugInfo(prev => `${prev}\n- Can open login URL: ${canOpen ? 'yes' : 'no'}`);
        
        // Check if we can open our own scheme
        const myAppUrl = 'myapp://test';
        const canOpenMyApp = await Linking.canOpenURL(myAppUrl);
        setDebugInfo(prev => `${prev}\n- Can open myapp:// scheme: ${canOpenMyApp ? 'yes' : 'no'}`);
      } catch (error) {
        console.error('Error in debug info:', error);
        setDebugInfo(prev => `${prev}\nError: ${error instanceof Error ? error.message : String(error)}`);
      }
    };
    
    logDebugInfo();

    // Cleanup subscription
    return () => {
      subscription.remove();
    };
  }, [navigation]);

  const handleLogin = async () => {
    try {
      // Show warning about potential disconnect
      setShowWarning(true);
      
      // Simple login approach - just open the backend login URL
      const loginUrl = `${BACKEND_URL}/auth/login`;
      console.log('Opening login URL:', loginUrl);
      setDebugInfo(prev => `${prev}\n\nOpening login URL: ${loginUrl}`);
      
      const supported = await Linking.canOpenURL(loginUrl);
      if (supported) {
        await Linking.openURL(loginUrl);
      } else {
        const errorMsg = "Don't know how to open URI: " + loginUrl;
        console.error(errorMsg);
        setDebugInfo(prev => `${prev}\nError: ${errorMsg}`);
        Alert.alert("Error", errorMsg);
      }
    } catch (error) {
      console.error('Failed to initiate login:', error);
      setDebugInfo(prev => `${prev}\nLogin error: ${error instanceof Error ? error.message : String(error)}`);
      Alert.alert('Error', 'Failed to open login page');
    }
  };

  const handleManualLogin = async () => {
    if (!manualToken || !manualUser) {
      Alert.alert('Error', 'Please enter both token and user ID');
      return;
    }

    try {
      // Store credentials
      await SecureStore.setItemAsync('oauth_token', manualToken);
      await SecureStore.setItemAsync('user_id', manualUser);
      console.log('Manual credentials stored successfully');
      setDebugInfo(prev => `${prev}\nManual credentials stored successfully`);

      // Navigate to test screen
      console.log('Navigating to Test screen...');
      setDebugInfo(prev => `${prev}\nNavigating to Test screen...`);
      
      navigation.reset({
        index: 0,
        routes: [{ name: 'Test' }],
      });
    } catch (error) {
      console.error('Error storing manual credentials:', error);
      setDebugInfo(prev => `${prev}\nERROR: ${error instanceof Error ? error.message : String(error)}`);
      Alert.alert('Error', 'Failed to store credentials');
    }
  };

  const openBrowserForLogin = async () => {
    // Open the login URL directly in the default browser on the device
    try {
      const loginUrl = `${BACKEND_URL}/auth/login`;
      const browsableUrl = loginUrl.replace('https://', 'https://');
      
      console.log('Opening browser with login URL:', browsableUrl);
      setDebugInfo(prev => `${prev}\nOpening browser with: ${browsableUrl}`);
      
      await Linking.openURL(browsableUrl);
      
      // Show instructions
      setTimeout(() => {
        Alert.alert(
          "Login Instructions",
          "1. Complete login in your browser\n" +
          "2. When you see 'Login Successful' page, copy your token and email\n" +
          "3. Return to this app\n" +
          "4. Enter the token and email in the form below",
          [{ text: "OK" }]
        );
      }, 1000);
    } catch (error) {
      console.error('Failed to open browser:', error);
      setDebugInfo(prev => `${prev}\nBrowser error: ${error instanceof Error ? error.message : String(error)}`);
      Alert.alert('Error', 'Failed to open browser');
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.scrollContainer}>
      <View style={styles.container}>
        <Text style={styles.title}>Oura Ring Login</Text>
        
        {showWarning ? (
          <View style={styles.warningBox}>
            <Text style={styles.warningTitle}>⚠️ Important: Read Before Proceeding</Text>
            <Text style={styles.warningText}>
              When you click "Login with Oura Ring" below, your browser will open for authentication.
              After completing the login:
            </Text>
            <Text style={styles.warningList}>
              1. You'll see a "Login Successful" page in Chrome{'\n'}
              2. When prompted, click "Open with Expo" (not "Open App"){'\n'}
              3. This will properly maintain the connection to the dev server{'\n'}
              4. You should see your token and user info in the app
            </Text>
            <View style={styles.warningButtons}>
              <TouchableOpacity 
                style={[styles.warningButton, styles.buttonPrimary]}
                onPress={handleLogin}
              >
                <Text style={styles.buttonText}>Login with Oura Ring</Text>
              </TouchableOpacity>
              <TouchableOpacity 
                style={[styles.warningButton, styles.buttonSecondary]}
                onPress={() => setShowWarning(false)}
              >
                <Text style={styles.buttonTextDark}>Go Back</Text>
              </TouchableOpacity>
            </View>
          </View>
        ) : (
          <>
            <View style={styles.loginOptions}>
              <Text style={styles.sectionHeading}>Login Options</Text>
              
              <View style={styles.optionCard}>
                <Text style={styles.optionTitle}>Option 1: Login with Oura Ring</Text>
                <Text style={styles.optionDescription}>
                  The app will open your browser for login. When redirected back, select "Open with Expo" 
                  when prompted (NOT "Open App").
                </Text>
                <TouchableOpacity 
                  style={[styles.button, styles.buttonPrimary]}
                  onPress={() => setShowWarning(true)}
                >
                  <Text style={styles.buttonText}>Login with Oura Ring</Text>
                </TouchableOpacity>
              </View>
              
              <View style={styles.optionCard}>
                <Text style={styles.optionTitle}>Option 2: Browser + Manual Entry</Text>
                <Text style={styles.optionDescription}>
                  Open your browser for login, then manually copy your credentials.
                  Use this if Option 1 doesn't work.
                </Text>
                <TouchableOpacity 
                  style={[styles.button, styles.buttonPrimary]}
                  onPress={openBrowserForLogin}
                >
                  <Text style={styles.buttonText}>Open Browser for Login</Text>
                </TouchableOpacity>
              </View>
            </View>
            
            <View style={styles.manualSection}>
              <Text style={styles.sectionHeading}>Manual Token Entry</Text>
              <Text style={styles.instructionText}>
                If automatic login didn't work, paste the values from the success page here:
              </Text>
              
              <Text style={styles.label}>Access Token:</Text>
              <TextInput
                style={styles.input}
                value={manualToken}
                onChangeText={setManualToken}
                placeholder="Paste your access token here"
              />
              
              <Text style={styles.label}>User ID (email):</Text>
              <TextInput
                style={styles.input}
                value={manualUser}
                onChangeText={setManualUser}
                placeholder="Enter your email"
              />
              
              <TouchableOpacity 
                style={[styles.button, styles.buttonPrimary, !manualToken || !manualUser ? styles.buttonDisabled : null]}
                onPress={handleManualLogin}
                disabled={!manualToken || !manualUser}
              >
                <Text style={styles.buttonText}>Use Manual Credentials</Text>
              </TouchableOpacity>
            </View>
          </>
        )}
        
        <TouchableOpacity 
          style={styles.debugButton}
          onPress={() => Alert.alert("Debug Info", debugInfo)}
        >
          <Text style={styles.debugButtonText}>Show Debug Info</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  scrollContainer: {
    flexGrow: 1,
    backgroundColor: '#f8f8f8',
  },
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    marginBottom: 25,
    color: '#333',
  },
  loginOptions: {
    width: '100%',
    marginBottom: 20,
  },
  optionCard: {
    backgroundColor: 'white',
    borderRadius: 10,
    padding: 15,
    marginBottom: 15,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 2,
  },
  optionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 8,
    color: '#333',
  },
  optionDescription: {
    fontSize: 14,
    marginBottom: 15,
    color: '#666',
    lineHeight: 20,
  },
  sectionHeading: {
    fontSize: 20,
    fontWeight: 'bold',
    marginVertical: 15,
    alignSelf: 'flex-start',
    color: '#333',
  },
  manualSection: {
    width: '100%',
    backgroundColor: 'white',
    borderRadius: 10,
    padding: 15,
    marginBottom: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 2,
  },
  instructionText: {
    fontSize: 14,
    color: '#666',
    marginBottom: 15,
    lineHeight: 20,
  },
  label: {
    fontSize: 16,
    fontWeight: '500',
    marginBottom: 5,
    color: '#333',
  },
  input: {
    width: '100%',
    height: 45,
    borderWidth: 1,
    borderColor: '#ccc',
    borderRadius: 5,
    marginBottom: 15,
    paddingHorizontal: 10,
    backgroundColor: '#fff',
  },
  button: {
    width: '100%',
    height: 45,
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: 5,
    marginVertical: 10,
  },
  buttonPrimary: {
    backgroundColor: '#4CAF50',
  },
  buttonSecondary: {
    backgroundColor: '#e0e0e0',
  },
  buttonDisabled: {
    backgroundColor: '#a5d6a7',
    opacity: 0.7,
  },
  buttonText: {
    color: 'white',
    fontSize: 16,
    fontWeight: '500',
  },
  buttonTextDark: {
    color: '#333',
    fontSize: 16,
    fontWeight: '500',
  },
  debugButton: {
    marginTop: 20,
    padding: 10,
  },
  debugButtonText: {
    color: '#888',
    fontSize: 14,
  },
  warningBox: {
    width: '100%',
    backgroundColor: '#fff3cd',
    borderColor: '#ffeeba',
    borderWidth: 1,
    borderRadius: 10,
    padding: 20,
    marginVertical: 20,
  },
  warningTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 10,
    color: '#856404',
  },
  warningText: {
    fontSize: 15,
    color: '#856404',
    marginBottom: 10,
    lineHeight: 22,
  },
  warningList: {
    fontSize: 15,
    color: '#856404',
    marginBottom: 15,
    lineHeight: 22,
    paddingLeft: 10,
  },
  warningButtons: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 10,
  },
  warningButton: {
    flex: 1,
    height: 45,
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: 5,
    marginHorizontal: 5,
  },
});

export default LoginScreen;
