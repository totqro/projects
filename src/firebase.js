// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getAnalytics } from "firebase/analytics";
// TODO: Add SDKs for Firebase products that you want to use
// https://firebase.google.com/docs/web/setup#available-libraries

// Your web app's Firebase configuration
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
  apiKey: "AIzaSyCDUpaU4en-SRDhOC7S6mvdZexF_jYSFTg",
  authDomain: "projects-brawlstars.firebaseapp.com",
  projectId: "projects-brawlstars",
  storageBucket: "projects-brawlstars.firebasestorage.app",
  messagingSenderId: "858378760819",
  appId: "1:858378760819:web:551aafd25538077a607006",
  measurementId: "G-6DDQCV2HKQ"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const analytics = getAnalytics(app);