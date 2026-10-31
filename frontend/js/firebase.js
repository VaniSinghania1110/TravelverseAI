import { initializeApp } from "https://www.gstatic.com/firebasejs/12.0.0/firebase-app.js";
import {
  getAuth,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  sendPasswordResetEmail,
  signOut,
  GoogleAuthProvider,
  signInWithPopup
} from "https://www.gstatic.com/firebasejs/12.0.0/firebase-auth.js";

const firebaseConfig = {
  apiKey: "AIzaSyDeNtYrUl2nrrTp5QpF0IoTb2rce2xxvAg",
  authDomain: "travelverse-fda35.firebaseapp.com",
  projectId: "travelverse-fda35",
  storageBucket: "travelverse-fda35.firebasestorage.app",
  messagingSenderId: "223773772845",
  appId: "1:223773772845:web:bee4f67669e5c8ae523ca4"
};

const app = initializeApp(firebaseConfig);

export const auth = getAuth(app);

export {
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  sendPasswordResetEmail,
  signOut,
  GoogleAuthProvider,
  signInWithPopup
};