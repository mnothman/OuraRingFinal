import 'dotenv/config';

export default {
  name: 'OuraRing',
  slug: 'OuraRing',
  version: '1.0.0',
  orientation: 'portrait',
  userInterfaceStyle: 'light',
  splash: {
    resizeMode: 'contain',
    backgroundColor: '#ffffff'
  },
  assetBundlePatterns: ['**/*'],
  ios: {
    supportsTablet: true,
    bundleIdentifier: 'com.yourcompany.ouraring',
    config: {
      usesNonExemptEncryption: false
    }
  },
  android: {
    adaptiveIcon: {
      backgroundColor: '#ffffff'
    },
    package: 'com.yourcompany.ouraring'
  },
  scheme: 'myapp',
  web: {
  },
  extra: {
    backendUrl: 'https://b33a-2601-207-380-fb60-d023-11f-59af-4505.ngrok-free.app'
  }
};
