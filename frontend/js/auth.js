import {
    auth,
    createUserWithEmailAndPassword
} from "./firebase.js";
const registerForm = document.getElementById("register-form");
registerForm.addEventListener("submit", async (e) => {

    e.preventDefault();

    const firstName = document.getElementById("first-name").value.trim();
    const lastName = document.getElementById("last-name").value.trim();
    const username = document.getElementById("username").value.trim();
    const email = document.getElementById("reg-email").value.trim();
    const password = document.getElementById("reg-password").value;

    try {

    const userCredential = await createUserWithEmailAndPassword(
        auth,
        email,
        password
    );

    console.log("User Created Successfully ✅");

    alert("Account Created Successfully!");

} catch (error) {

    console.error(error);

    if (error.code === "auth/email-already-in-use") {

        alert("This email is already registered.");

    }
    else if (error.code === "auth/weak-password") {

        alert("Password must be at least 6 characters.");

    }
    else if (error.code === "auth/invalid-email") {

        alert("Please enter a valid email address.");

    }
    else {

        alert(error.message);

    }

}

});
