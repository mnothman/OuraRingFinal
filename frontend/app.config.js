import 'dotenv/config';

export default {
  expo: {
    name: "OuraRingFinal",
    slug: "ouraringfinal",
    extra: {
      CLIENT_ID: process.env.CLIENT_ID,
      REDIRECT_URI: process.env.REDIRECT_URI,
    },
  },
};
