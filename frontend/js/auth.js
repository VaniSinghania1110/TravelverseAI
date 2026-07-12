import {
    auth,
    createUserWithEmailAndPassword,
    signInWithEmailAndPassword
} from "./firebase.js";


// ===============================
// TRAVELVERSE TOAST
// ===============================

function showToast(type, title, message) {

    const toast = document.getElementById("travel-toast");
    const toastIcon = document.getElementById("toast-icon");
    const toastTitle = document.getElementById("toast-title");
    const toastMessage = document.getElementById("toast-message");

    toast.classList.remove("success", "error");
    toast.classList.add(type);

    toastIcon.textContent = type === "success" ? "✓" : "!";
    toastTitle.textContent = title;
    toastMessage.textContent = message;

    toast.classList.add("show");

    clearTimeout(window.travelToastTimer);

    window.travelToastTimer = setTimeout(() => {
        toast.classList.remove("show");
    }, 4000);
}


document
    .getElementById("toast-close")
    .addEventListener("click", () => {

        document
            .getElementById("travel-toast")
            .classList.remove("show");

    });


// ===============================
// SIGNUP
// ===============================

const registerForm = document.getElementById("register-form");

registerForm.addEventListener("submit", async (e) => {

    e.preventDefault();

    const firstName = document
        .getElementById("first-name")
        .value
        .trim();

    const lastName = document
        .getElementById("last-name")
        .value
        .trim();

    const username = document
        .getElementById("username")
        .value
        .trim();

    const email = document
        .getElementById("reg-email")
        .value
        .trim();

    const password = document
        .getElementById("reg-password")
        .value;

    try {

        // CREATE FIREBASE USER

        const userCredential =
            await createUserWithEmailAndPassword(
                auth,
                email,
                password
            );

        const firebaseUser = userCredential.user;


        // SEND USER TO FASTAPI

        const response = await fetch(
            "http://127.0.0.1:8000/register",
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    first_name: firstName,
                    last_name: lastName,
                    username: username,
                    email: email,
                    firebase_uid: firebaseUser.uid
                })
            }
        );


        const backendData = await response.json();

        if (!response.ok) {
            throw new Error(
                backendData.detail || "Account creation failed"
            );
        }

        console.log(
            "Backend Response:",
            backendData
        );

        console.log(
            "User Created Successfully ✅"
        );


        // SHOW BIG CENTER MODAL

        const successModal =
            document.getElementById(
                "account-success-modal"
            );

        successModal.classList.add("show");


    } catch (error) {

        console.error(error);


        if (
            error.code ===
            "auth/email-already-in-use"
        ) {

            showToast(
                "error",
                "Account already exists",
                "This email is already registered. Try logging in instead."
            );

        }

        else if (
            error.code === "auth/weak-password"
        ) {

            showToast(
                "error",
                "Password too weak",
                "Password must be at least 6 characters."
            );

        }

        else if (
            error.code === "auth/invalid-email"
        ) {

            showToast(
                "error",
                "Invalid email",
                "Please enter a valid email address."
            );

        }

        else {

            showToast(
                "error",
                "Something went wrong",
                error.message
            );

        }

    }

});


// ===============================
// LOGIN
// ===============================

const loginForm =
    document.getElementById("login-form");


loginForm.addEventListener(
    "submit",
    async (e) => {

        e.preventDefault();

        const email = document
            .getElementById("login-email")
            .value
            .trim();

        const password = document
            .getElementById("login-password")
            .value;

        try {

            // FIREBASE LOGIN

            const userCredential =
                await signInWithEmailAndPassword(
                    auth,
                    email,
                    password
                );

            const firebaseUser =
                userCredential.user;


            console.log(
                "Logged in Firebase User:",
                firebaseUser.uid
            );


            // GET USER FROM FASTAPI

            const response = await fetch(
                `http://127.0.0.1:8000/login/${firebaseUser.uid}`
            );


            const backendData =
                await response.json();


            if (!response.ok) {

                throw new Error(
                    backendData.detail ||
                    "Backend login failed"
                );

            }


            console.log(
                "Backend Login Response:",
                backendData
            );


            // SAVE USER LOCALLY

            localStorage.setItem(
                "travelverse_user",
                JSON.stringify(
                    backendData.user
                )
            );


            // LOGIN SUCCESS TOAST

            showToast(
                "success",
                "Welcome back!",
                "Login successful. Your next adventure awaits."
            );


            console.log(
                "Saved User:",
                backendData.user
            );


        } catch (error) {

            console.error(error);


            if (
                error.code ===
                "auth/invalid-credential" ||

                error.code ===
                "auth/wrong-password" ||

                error.code ===
                "auth/user-not-found"
            ) {

                showToast(
                    "error",
                    "Couldn't log you in",
                    "The email or password you entered is incorrect."
                );

            }

            else {

                showToast(
                    "error",
                    "Something went wrong",
                    error.message
                );

            }

        }

    }
);


// ===============================
// SUCCESS MODAL BUTTON
// ===============================

const successModalBtn =
    document.getElementById(
        "success-modal-btn"
    );


successModalBtn.addEventListener(
    "click",
    () => {

        document
            .getElementById(
                "account-success-modal"
            )
            .classList
            .remove("show");

    }
);