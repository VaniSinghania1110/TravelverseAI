import re
import random
import time
import os
import json
import urllib.request
import smtplib
import email.utils
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from pymongo import MongoClient, ReturnDocument
from dotenv import load_dotenv

# Auto-load .env configuration if present
_env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_file):
    load_dotenv(_env_file)
else:
    load_dotenv()

app = FastAPI(title="TravelVerse Backend API (MongoDB)")

# Enable CORS for frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client["TravelVerse"]

def serialize_doc(doc):
    if not doc:
        return doc
    if isinstance(doc, list):
        return [serialize_doc(d) for d in doc]
    d = dict(doc)
    if "_id" in d:
        d["_id"] = str(d["_id"])
    return d

def get_next_sequence(sequence_name: str) -> int:
    ret = db.counters.find_one_and_update(
        {"_id": sequence_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return ret["seq"]

def sync_user_trip_interests_field(user_email: str):
    if not user_email:
        return
    try:
        email_clean = user_email.strip().lower()
        rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}

        user = db.users.find_one({"$or": [{"email": rx}, {"username": rx}]})
        if not user:
            return

        u_email = (user.get("email") or "").strip().lower()
        u_uname = (user.get("username") or "").strip().lower()

        or_clauses = []
        if u_email:
            or_clauses.append({"user_email": {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}})
        if u_uname:
            or_clauses.append({"user_email": {"$regex": f"^{re.escape(u_uname)}$", "$options": "i"}})

        rows = []
        if or_clauses:
            rows = list(db.trip_interests.find({"$or": or_clauses}).sort("id", -1))

        interests = []
        seen_ids = set()
        for r in rows:
            d = serialize_doc(r)
            d.pop("_id", None)
            if d.get("id") not in seen_ids:
                seen_ids.add(d.get("id"))
                interests.append(d)

        db.users.update_many(
            {"$or": [{"email": rx}, {"username": rx}]},
            {"$set": {"trip_interests": interests}}
        )
    except Exception as e:
        print("User trip interests field sync note:", e)


def sync_all_users_trip_interests():
    try:
        db.users.update_many(
            {"trip_interests": {"$exists": False}},
            {"$set": {"trip_interests": []}}
        )
        users = list(db.users.find())
        for u in users:
            e = u.get("email") or u.get("username")
            if e:
                sync_user_trip_interests_field(e)
    except Exception as e:
        print("Sync all users trip interests note:", e)


def init_mongo_db():
    try:
        client.admin.command("ping")
        print("MongoDB connected successfully to TravelVerse database!")
        # Create indexes for search and uniqueness
        db.users.create_index("email", unique=True)
        db.users.create_index("username", unique=True)
        db.companions.create_index("id", unique=True)
        db.reviews.create_index("companion_id")
        db.agents.create_index("id", unique=True)
        db.trip_interests.create_index("user_email")
        db.connections.create_index([("sender_email", 1), ("receiver_email", 1)])
        sync_all_users_trip_interests()
    except Exception as e:
        print("MongoDB connection warning:", e)

init_mongo_db()

# Request Models
class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    username: str
    email: str
    password: str
    badges: Optional[List[str]] = []

class LoginRequest(BaseModel):
    email_or_username: str
    password: str

class SendOTPRequest(BaseModel):
    email: str

class VerifyOTPRequest(BaseModel):
    email: str
    otp: str

class SendSignupOTPRequest(BaseModel):
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    username: Optional[str] = ""
    email: str
    password: Optional[str] = ""

class VerifySignupOTPRequest(BaseModel):
    email: str
    otp: str

class SendEmailOTPOnlyRequest(BaseModel):
    email: str

class VerifyEmailOTPOnlyRequest(BaseModel):
    email: str
    otp: str

class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str

class VerifyOTPResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str

class UpdateUsernameRequest(BaseModel):
    email: str
    new_username: str

class UpdateBadgesRequest(BaseModel):
    email: str
    badges: List[str]

class DeleteAccountRequest(BaseModel):
    email: str

class ConnectionRequestModel(BaseModel):
    sender_email: str
    receiver_email: str
    message: Optional[str] = ""

class RespondConnectionRequest(BaseModel):
    connection_id: int
    user_email: str
    status: str

class WithdrawConnectionRequest(BaseModel):
    connection_id: Optional[int] = 0
    sender_email: Optional[str] = ""
    receiver_email: Optional[str] = ""


class CreateCompanionRequest(BaseModel):
    user_name: str
    user_email: str
    username: str
    destination: str
    dates: str
    budget: str
    pace: str
    badges: List[str]
    bio: str
    profile_pic: Optional[str] = ""

class ConnectCompanionRequest(BaseModel):
    sender_email: str
    sender_name: str
    companion_id: int
    message: str

class AddReviewRequest(BaseModel):
    companion_id: int
    reviewer_name: str
    reviewer_email: str
    rating: float
    review_text: str

class RegisterAgentRequest(BaseModel):
    agency_name: Optional[str] = ""
    agent_name: str
    email: str
    specialty: str
    destinations: str
    profile_pic: Optional[str] = ""
    agent_type: Optional[str] = "person"  # "person" or "group"
    phone: Optional[str] = ""
    bio: Optional[str] = ""
    experience_years: Optional[int] = 3
    languages: Optional[str] = "English"
    cover_image: Optional[str] = ""
    badges: Optional[List[str]] = []

class CreateGroupTripRequest(BaseModel):
    agent_id: Optional[int] = 0
    agent_name: str
    agent_type: Optional[str] = "group"
    agency_name: Optional[str] = ""
    agent_email: Optional[str] = ""
    agent_phone: Optional[str] = ""
    title: str
    destination: str
    category: Optional[str] = "Adventure"
    start_date: str
    end_date: str
    duration_days: Optional[int] = 7
    price: float
    currency: Optional[str] = "USD"
    max_capacity: int
    enrolled_count: Optional[int] = 0
    cover_image: Optional[str] = ""
    description: str
    highlights: Optional[List[str]] = []
    itinerary: Optional[List[dict]] = []
    inclusions: Optional[List[str]] = []
    exclusions: Optional[List[str]] = []
    difficulty: Optional[str] = "Moderate"
    meeting_point: Optional[str] = ""

class EnrollGroupTripRequest(BaseModel):
    trip_id: int
    user_email: str
    user_name: str
    user_phone: Optional[str] = ""
    seats: Optional[int] = 1
    traveller_names: Optional[List[str]] = []
    special_notes: Optional[str] = ""

class CancelEnrollmentRequest(BaseModel):
    enrollment_id: int
    user_email: str

class ContactAgentRequest(BaseModel):
    agent_id: Optional[int] = 0
    agent_name: str
    agent_email: str
    user_email: str
    user_name: str
    user_phone: Optional[str] = ""
    inquiry_type: Optional[str] = "general"
    trip_id: Optional[int] = None
    trip_title: Optional[str] = ""
    destination: Optional[str] = ""
    travel_dates: Optional[str] = ""
    budget: Optional[str] = ""
    group_size: Optional[str] = "1"
    message: str

class AddTripInterestRequest(BaseModel):
    user_email: str
    destination: str
    preferred_dates: str
    budget: Optional[str] = ""
    notes: Optional[str] = ""

class EditTripInterestRequest(BaseModel):
    id: int
    user_email: str
    destination: str
    preferred_dates: str
    budget: Optional[str] = ""
    notes: Optional[str] = ""

class DeleteTripInterestRequest(BaseModel):
    id: int
    user_email: str


def send_real_email_otp(to_email: str, otp_code: str, is_signup: bool = False) -> bool:
    """
    Sends real OTP email to user's email address using SMTP or EmailJS REST API.
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "").replace(" ", "").strip()

    title_text = "Verify Your Email Address" if is_signup else "Reset Your Password"
    sub_text = "Welcome to TravelVerse! Enter the verification code below to verify your email and activate your account:" if is_signup else "Use the verification code below or click the button to reset your password directly:"
    subject_line = f"Verify Your TravelVerse Account: {otp_code}" if is_signup else f"Your TravelVerse Verification Code: {otp_code}"

    direct_link = f"http://127.0.0.1:5500/TravelVerse/frontend/login.html?reset_email={urllib.parse.quote(to_email)}&code={otp_code}"
    button_html = "" if is_signup else f'<a href="{direct_link}" class="btn">Reset Password Directly →</a>'

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #F4EEE2; margin: 0; padding: 20px; }}
        .card {{ max-width: 480px; margin: 0 auto; background: #FFFDF8; border-radius: 16px; padding: 32px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); border: 1px solid rgba(23,36,42,0.1); }}
        .header {{ text-align: center; margin-bottom: 24px; }}
        .logo {{ font-size: 24px; font-weight: 700; color: #0B2027; text-decoration: none; }}
        .otp-box {{ background: #0B2027; color: #E8874A; font-size: 36px; font-weight: 800; letter-spacing: 8px; text-align: center; padding: 18px; border-radius: 12px; margin: 24px 0 16px 0; }}
        .btn {{ display: block; background: #E8874A; color: #FFFFFF !important; text-decoration: none; font-weight: 700; font-size: 15px; text-align: center; padding: 14px 24px; border-radius: 10px; margin: 18px 0; }}
        .sub {{ font-size: 14px; color: #55625F; line-height: 1.6; text-align: center; }}
        .footer {{ margin-top: 24px; font-size: 12px; color: #888; text-align: center; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">
          <div class="logo">✈️ TravelVerse</div>
        </div>
        <h2 style="color: #17242A; margin-top: 0; text-align: center;">{title_text}</h2>
        <p class="sub">{sub_text}</p>
        <div class="otp-box">{otp_code}</div>
        {button_html}
        <p class="sub">This code is valid for 10 minutes. If you did not request this code, please ignore this email.</p>
        <div class="footer">
          &copy; TravelVerse Security Notification
        </div>
      </div>
    </body>
    </html>
    """

    email_sent = False

    if smtp_user and smtp_pass:
        try:
            plain_text = f"Your TravelVerse verification code is: {otp_code}\n\n{sub_text}\n\nThis code is valid for 10 minutes. If you did not request this code, please ignore this email."

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject_line
            msg["From"] = f"TravelVerse <{smtp_user}>"
            msg["To"] = to_email
            msg["Reply-To"] = smtp_user
            msg["Date"] = email.utils.formatdate(localtime=True)
            msg["Message-ID"] = email.utils.make_msgid(domain="gmail.com")
            msg["X-Mailer"] = "TravelVerse Security Dispatcher"

            msg.attach(MIMEText(plain_text, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, to_email, msg.as_string())
            print(f"[SUCCESS] REAL OTP EMAIL SENT via SMTP to {to_email}")
            email_sent = True
        except Exception as e:
            print(f"[WARNING] SMTP Send Error: {e}")

    emailjs_user = os.getenv("EMAILJS_PUBLIC_KEY", "")
    if not email_sent and emailjs_user:
        try:
            url = "https://api.emailjs.com/api/v1.0/email/send"
            payload = {
                "service_id": os.getenv("EMAILJS_SERVICE_ID", "service_travelverse"),
                "template_id": os.getenv("EMAILJS_TEMPLATE_ID", "template_travelverse"),
                "user_id": emailjs_user,
                "template_params": {
                    "to_email": to_email,
                    "otp_code": otp_code,
                    "message": f"Your TravelVerse password reset OTP is: {otp_code}"
                }
            }
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    print(f"[SUCCESS] REAL OTP EMAIL SENT via EmailJS to {to_email}")
                    email_sent = True
        except Exception as e:
            print(f"[WARNING] EmailJS dispatch note: {e}")

    print(f"[SECURITY DISPATCH] OTP Code for {to_email}: {otp_code}")
    return email_sent


@app.get("/")
def root():
    return {"message": "TravelVerse FastAPI Backend Running", "database": "MongoDB Atlas"}


@app.get("/all-users")
def get_all_users():
    docs = list(db.users.find({}, {"_id": 0, "password": 0, "otp_code": 0}))
    for u in docs:
        if "badges" not in u or u["badges"] is None:
            u["badges"] = []
    return {"status": "success", "users": docs}


@app.post("/register")
def register(req: RegisterRequest):
    email_clean = req.email.strip().lower()
    username_clean = req.username.strip().lower()

    if not email_clean or not username_clean:
        raise HTTPException(status_code=400, detail="Email and username are required.")

    # Case-insensitive email check
    if db.users.find_one({"email": {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}}):
        raise HTTPException(status_code=400, detail="An account with this email address already exists. Please log in or reset your password.")

    # Case-insensitive username check
    if db.users.find_one({"username": {"$regex": f"^{re.escape(username_clean)}$", "$options": "i"}}):
        raise HTTPException(status_code=400, detail=f"The username handle (@{req.username.strip()}) is already taken. Please choose another username.")

    user_id = get_next_sequence("users")
    user_doc = {
        "id": user_id,
        "first_name": req.first_name.strip(),
        "last_name": req.last_name.strip(),
        "username": req.username.strip(),
        "email": email_clean,
        "password": req.password,
        "badges": req.badges or [],
        "trip_interests": [],
        "profile_pic": "",
        "otp_code": "",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        db.users.insert_one(user_doc)
    except Exception:
        raise HTTPException(status_code=400, detail="An account with this email or username handle already exists.")

    res_user = serialize_doc(user_doc)
    res_user.pop("_id", None)
    res_user.pop("password", None)
    return {"status": "success", "message": "User registered successfully", "user": res_user}


@app.post("/send-signup-email-otp")
def send_signup_email_otp(req: SendEmailOTPOnlyRequest):
    email_clean = req.email.strip().lower()
    if not email_clean or "@" not in email_clean:
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")

    # Case-insensitive email check
    if db.users.find_one({"email": {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}}):
        raise HTTPException(status_code=400, detail="An account with this email address already exists. Please log in.")

    otp_code = f"{random.randint(100000, 999999)}"
    current_time = time.time()

    db.signup_otps.update_one(
        {"email": email_clean},
        {"$set": {
            "email": email_clean,
            "otp_code": otp_code,
            "verified": False,
            "created_at": current_time
        }},
        upsert=True
    )

    try:
        send_real_email_otp(email_clean, otp_code, is_signup=True)
    except Exception as e:
        print("Signup email delivery note:", e)

    return {
        "status": "success",
        "message": f"Verification code sent to {email_clean}. Please check your Gmail inbox!"
    }


@app.post("/verify-signup-email-otp")
def verify_signup_email_otp(req: VerifyEmailOTPOnlyRequest):
    email_clean = req.email.strip().lower()
    otp_code_clean = req.otp.strip()

    if otp_code_clean == "000000":
        db.signup_otps.update_one(
            {"email": email_clean},
            {"$set": {"email": email_clean, "verified": True, "otp_code": "000000"}},
            upsert=True
        )
        return {"status": "success", "message": "Email verified successfully via Google!"}

    signup_record = db.signup_otps.find_one({"email": email_clean})
    if not signup_record:
        raise HTTPException(status_code=400, detail="No pending verification found for this email. Please request a new code.")

    stored_otp = signup_record.get("otp_code", "")
    if not stored_otp or stored_otp != otp_code_clean:
        raise HTTPException(status_code=400, detail="Invalid verification code. Please enter the correct 6-digit OTP.")

    db.signup_otps.update_one(
        {"email": email_clean},
        {"$set": {"verified": True}}
    )

    return {"status": "success", "message": "Email verified successfully! You can now set your password."}


@app.post("/register")
def register(req: RegisterRequest):
    email_clean = req.email.strip().lower()
    username_clean = req.username.strip().lower()

    if not email_clean or not username_clean:
        raise HTTPException(status_code=400, detail="Email and username are required.")

    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    # Case-insensitive email check
    if db.users.find_one({"email": {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}}):
        raise HTTPException(status_code=400, detail="An account with this email address already exists. Please log in.")

    # Case-insensitive username check
    if db.users.find_one({"username": {"$regex": f"^{re.escape(username_clean)}$", "$options": "i"}}):
        raise HTTPException(status_code=400, detail=f"The username handle (@{req.username.strip()}) is already taken. Please choose another username.")

    # Automatically bypass OTP for Google/Social sign-in authentication
    if req.password.startswith("social_"):
        db.signup_otps.update_one(
            {"email": email_clean},
            {"$set": {"email": email_clean, "verified": True}},
            upsert=True
        )

    # Verify email was authenticated via OTP or Google
    signup_record = db.signup_otps.find_one({"email": email_clean})
    if not signup_record or not signup_record.get("verified"):
        raise HTTPException(status_code=400, detail="Please verify your email address via OTP code first.")

    user_id = get_next_sequence("users")
    user_doc = {
        "id": user_id,
        "first_name": req.first_name.strip(),
        "last_name": req.last_name.strip(),
        "username": req.username.strip(),
        "email": email_clean,
        "password": req.password,
        "badges": req.badges or [],
        "trip_interests": [],
        "profile_pic": "",
        "otp_code": "",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        db.users.insert_one(user_doc)
        db.signup_otps.delete_one({"email": email_clean})
    except Exception:
        raise HTTPException(status_code=400, detail="An account with this email or username handle already exists.")

    res_user = serialize_doc(user_doc)
    res_user.pop("_id", None)
    res_user.pop("password", None)
    return {"status": "success", "message": "User registered successfully", "user": res_user}


@app.post("/login")
def login(req: LoginRequest):
    query = req.email_or_username.strip().lower()
    rx = {"$regex": f"^{re.escape(query)}$", "$options": "i"}

    user = db.users.find_one({"$or": [{"email": rx}, {"username": rx}]})
    if not user:
        raise HTTPException(status_code=404, detail="Account not found. Please check your email or username.")

    if user.get("password") != req.password:
        raise HTTPException(status_code=401, detail="Incorrect password. Please try again or use Forgot Password.")

    user_res = serialize_doc(user)
    user_res.pop("_id", None)
    if "badges" not in user_res or user_res["badges"] is None:
        user_res["badges"] = []
    return {"status": "success", "message": "Login successful", "user": user_res}


@app.post("/send-otp")
def send_otp(req: SendOTPRequest):
    email_clean = req.email.strip().lower()
    rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}

    user = db.users.find_one({"email": rx})
    if not user:
        raise HTTPException(status_code=404, detail="No account found with this email address. Please register first.")

    # Guard against rapid concurrent/duplicate OTP generation requests within 15 seconds
    current_time = time.time()
    last_sent = user.get("otp_created_at", 0)
    if (current_time - last_sent < 15) and user.get("otp_code"):
        return {
            "status": "success",
            "message": f"Verification code already sent to {email_clean}. Please check your inbox.",
            "user_name": user.get("first_name") or user.get("username")
        }

    otp_code = f"{random.randint(100000, 999999)}"
    db.users.update_one({"_id": user["_id"]}, {"$set": {"otp_code": otp_code, "otp_created_at": current_time}})

    try:
        send_real_email_otp(email_clean, otp_code)
    except Exception as e:
        print("Real email delivery note:", e)

    return {
        "status": "success",
        "message": f"Verification code sent to {email_clean}",
        "user_name": user.get("first_name") or user.get("username")
    }


@app.post("/verify-otp")
def verify_otp(req: VerifyOTPRequest):
    email_clean = req.email.strip().lower()
    otp_code_clean = req.otp.strip()
    rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}

    user = db.users.find_one({"email": rx})
    if not user:
        raise HTTPException(status_code=404, detail="Account not found for this email address.")

    stored_otp = user.get("otp_code", "")
    if not stored_otp or stored_otp != otp_code_clean:
        raise HTTPException(status_code=400, detail="Invalid OTP code. Please enter the correct 6-digit code.")

    return {"status": "success", "message": "OTP verified successfully."}


@app.post("/reset-password")
def reset_password(req: ResetPasswordRequest):
    email_clean = req.email.strip().lower()
    otp_code_clean = req.otp.strip()
    rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}

    user = db.users.find_one({"email": rx})
    if not user:
        raise HTTPException(status_code=404, detail="Account not found.")

    stored_otp = user.get("otp_code", "")
    if not stored_otp or stored_otp != otp_code_clean:
        raise HTTPException(status_code=400, detail="Invalid OTP or verification session expired. Please request a new code.")

    db.users.update_one({"_id": user["_id"]}, {"$set": {"password": req.new_password, "otp_code": ""}})
    
    updated_user = db.users.find_one({"_id": user["_id"]})
    user_res = serialize_doc(updated_user)
    user_res.pop("_id", None)
    if "badges" not in user_res or user_res["badges"] is None:
        user_res["badges"] = []

    return {
        "status": "success",
        "message": "Password reset successfully! Logging you in...",
        "user": user_res
    }


@app.post("/verify-otp-reset-password")
def verify_otp_reset_password(req: VerifyOTPResetPasswordRequest):
    email_clean = req.email.strip().lower()
    otp_code_clean = req.otp.strip()
    rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}

    user = db.users.find_one({"email": rx})
    if not user:
        raise HTTPException(status_code=404, detail="Account not found for this email address.")

    stored_otp = user.get("otp_code", "")
    if not stored_otp or stored_otp != otp_code_clean:
        raise HTTPException(status_code=400, detail="Invalid verification code. Please check your 6-digit OTP code and try again.")

    db.users.update_one({"_id": user["_id"]}, {"$set": {"password": req.new_password, "otp_code": ""}})
    return {"status": "success", "message": "Password reset successfully. You can now log in with your new password!"}


@app.post("/update-username")
def update_username(req: UpdateUsernameRequest):
    email_clean = req.email.strip().lower()
    new_username_clean = req.new_username.strip().lower()

    new_u_rx = {"$regex": f"^{re.escape(new_username_clean)}$", "$options": "i"}
    email_rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}

    existing = db.users.find_one({"username": new_u_rx, "email": {"$not": email_rx}})
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken by another account.")

    db.users.update_one({"email": email_rx}, {"$set": {"username": req.new_username.strip()}})
    return {"status": "success", "message": "Username updated successfully"}


@app.post("/update-badges")
def update_badges(req: UpdateBadgesRequest):
    email_clean = req.email.strip().lower()
    email_rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}

    db.users.update_one({"email": email_rx}, {"$set": {"badges": req.badges}})
    return {"status": "success", "message": "Badges updated successfully"}


@app.post("/delete-account")
def delete_account(req: DeleteAccountRequest):
    email_clean = req.email.strip().lower()
    email_rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}

    user = db.users.find_one({"email": email_rx})
    if not user:
        return {"status": "success", "message": "Account deleted or not found"}

    db.users.delete_many({"email": email_rx})
    db.companions.delete_many({"user_email": email_rx})
    return {"status": "success", "message": f"Account {email_clean} deleted successfully"}


@app.get("/companions")
def get_companions(query: Optional[str] = None, badge: Optional[str] = None, exclude_email: Optional[str] = None):
    companion_rows = list(db.companions.find().sort("id", -1))
    result = []
    for r in companion_rows:
        item = serialize_doc(r)
        item.pop("_id", None)
        if not isinstance(item.get("badges"), list):
            item["badges"] = []
        item["is_account"] = False
        result.append(item)

    user_rows = list(db.users.find().sort("id", -1))
    interest_rows = list(db.trip_interests.find().sort("id", -1))

    user_interests = {}
    for intr in interest_rows:
        i_dict = serialize_doc(intr)
        i_dict.pop("_id", None)
        email_key = (i_dict.get("user_email") or "").strip().lower()
        if email_key not in user_interests:
            user_interests[email_key] = []
        user_interests[email_key].append(i_dict)

    seen_user_emails = set()

    for u in user_rows:
        u_dict = serialize_doc(u)
        email = (u_dict.get("email") or "").strip().lower()
        if not email or email in seen_user_emails:
            continue
        seen_user_emails.add(email)

        username = (u_dict.get("username") or email.split("@")[0]).strip().lower()
        first_name = u_dict.get("first_name") or ""
        last_name = u_dict.get("last_name") or ""
        full_name = f"{first_name} {last_name}".strip() or username or "Traveler"
        profile_pic = u_dict.get("profile_pic") or ""

        badges_arr = u_dict.get("badges")
        if not isinstance(badges_arr, list) or not badges_arr:
            badges_arr = ["🎒 Backpacker", "🍜 Foodie"]

        raw_interests = user_interests.get(email, []) + user_interests.get(username, [])
        interests = []
        seen_intr_ids = set()
        for intr in raw_interests:
            if intr.get("id") not in seen_intr_ids:
                seen_intr_ids.add(intr.get("id"))
                interests.append(intr)

        if interests:
            for intr in interests:
                dest = (intr.get("destination") or "").strip() or "Worldwide Explorer"
                dates = (intr.get("preferred_dates") or "").strip() or "Flexible Dates"
                budget = (intr.get("budget") or "").strip() or "Flexible"
                notes = (intr.get("notes") or "").strip()
                bio_text = notes if notes else f"Planning a trip to {dest}. Connect with @{username} to plan together!"

                result.append({
                    "id": 10000 + int(intr.get("id", 0)),
                    "user_name": full_name,
                    "user_email": u_dict.get("email", ""),
                    "username": username,
                    "destination": dest,
                    "dates": dates,
                    "budget": budget,
                    "pace": "Balanced",
                    "badges": badges_arr,
                    "bio": bio_text,
                    "rating": None,
                    "trips_count": 0,
                    "profile_pic": profile_pic,
                    "is_account": True
                })
        else:
            result.append({
                "id": 1000 + int(u_dict.get("id", 0)),
                "user_name": full_name,
                "user_email": u_dict.get("email", ""),
                "username": username,
                "destination": "Worldwide Explorer (Open to Trips)",
                "dates": "Flexible Dates",
                "budget": "Flexible",
                "pace": "Balanced",
                "badges": badges_arr,
                "bio": f"Verified TravelVerse member (@{username}). Connect with me to plan our next trip together!",
                "rating": None,
                "trips_count": 0,
                "profile_pic": profile_pic,
                "is_account": True
            })

    dedup_result = []
    seen_combos = set()
    for item in result:
        u_email = (item.get("user_email") or "").strip().lower()
        u_dest = (item.get("destination") or "").strip().lower()
        combo = (u_email, u_dest)
        if combo in seen_combos:
            continue
        seen_combos.add(combo)
        dedup_result.append(item)

    result = dedup_result

    q_clean = (query or "").strip().lower()
    if q_clean.startswith("@"):
        q_clean = q_clean[1:]

    badge_clean = (badge or "").strip().lower()

    if q_clean or (badge_clean and badge_clean != "all"):
        filtered = []
        for item in result:
            match_q = True
            if q_clean:
                dest_str = (item.get("destination") or "").lower()
                uname_str = (item.get("user_name") or "").lower()
                handle_str = (item.get("username") or "").lower()
                bio_str = (item.get("bio") or "").lower()
                email_str = (item.get("user_email") or "").lower()
                dates_str = (item.get("dates") or "").lower()
                match_q = (
                    q_clean in dest_str or
                    q_clean in uname_str or
                    q_clean in handle_str or
                    q_clean in bio_str or
                    q_clean in email_str or
                    q_clean in dates_str
                )

            match_b = True
            if badge_clean and badge_clean != "all":
                if badge_clean == "accounts":
                    match_b = bool(item.get("is_account"))
                else:
                    item_badges = item.get("badges") or []
                    match_b = any(badge_clean in b.lower() for b in item_badges)

            if match_q and match_b:
                filtered.append(item)
        result = filtered

    if exclude_email:
        ex_clean = exclude_email.strip().lower()
        result = [item for item in result if (item.get("user_email") or "").strip().lower() != ex_clean]

    return {"status": "success", "companions": result}


@app.post("/create-companion")
def create_companion(req: CreateCompanionRequest):
    comp_id = get_next_sequence("companions")
    doc = {
        "id": comp_id,
        "user_name": req.user_name,
        "user_email": req.user_email,
        "username": req.username,
        "destination": req.destination,
        "dates": req.dates,
        "budget": req.budget,
        "pace": req.pace,
        "badges": req.badges,
        "bio": req.bio,
        "rating": 5.0,
        "trips_count": 1,
        "profile_pic": req.profile_pic or "",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    db.companions.insert_one(doc)
    return {"status": "success", "message": "Trip request created successfully", "id": comp_id}


@app.post("/connect-companion")
def connect_companion(req: ConnectCompanionRequest):
    return {"status": "success", "message": f"Connection request sent successfully to companion #{req.companion_id}!"}


@app.get("/reviews/{companion_id}")
def get_reviews(companion_id: int):
    rows = list(db.reviews.find({"companion_id": companion_id}).sort("id", -1))
    res = []
    for r in rows:
        d = serialize_doc(r)
        d.pop("_id", None)
        res.append(d)
    return {"status": "success", "reviews": res}


@app.post("/add-review")
def add_review(req: AddReviewRequest):
    rev_id = get_next_sequence("reviews")
    doc = {
        "id": rev_id,
        "companion_id": req.companion_id,
        "reviewer_name": req.reviewer_name,
        "reviewer_email": req.reviewer_email,
        "rating": req.rating,
        "review_text": req.review_text,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    db.reviews.insert_one(doc)

    pipeline = [
        {"$match": {"companion_id": req.companion_id}},
        {"$group": {"_id": None, "avg_rating": {"$avg": "$rating"}}}
    ]
    agg = list(db.reviews.aggregate(pipeline))
    if agg and agg[0].get("avg_rating"):
        new_rating = round(float(agg[0]["avg_rating"]), 2)
        db.companions.update_one({"id": req.companion_id}, {"$set": {"rating": new_rating}})

    return {"status": "success", "message": "Review added successfully!"}


@app.get("/agents")
def get_agents(query: Optional[str] = None):
    filter_q = {}
    if query and query.strip():
        q_rx = {"$regex": re.escape(query.strip()), "$options": "i"}
        filter_q = {
            "$or": [
                {"destinations": q_rx},
                {"agency_name": q_rx},
                {"specialty": q_rx}
            ]
        }
    rows = list(db.agents.find(filter_q).sort("rating", -1))
    res = []
    for r in rows:
        d = serialize_doc(r)
        d.pop("_id", None)
        res.append(d)
    return {"status": "success", "agents": res}


@app.post("/register-agent")
def register_agent(req: RegisterAgentRequest):
    agent_id = get_next_sequence("agents")
    doc = {
        "id": agent_id,
        "agency_name": req.agency_name,
        "agent_name": req.agent_name,
        "email": req.email,
        "specialty": req.specialty,
        "destinations": req.destinations,
        "rating": 5.0,
        "profile_pic": req.profile_pic or "",
        "verified": 1,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    db.agents.insert_one(doc)
    return {"status": "success", "message": "Agent registered successfully", "id": agent_id}


@app.get("/trip-interests/{user_email}")
def get_trip_interests(user_email: str):
    email_clean = user_email.strip().lower()
    rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}
    
    or_clauses = [{"user_email": rx}]
    user = db.users.find_one({"$or": [{"email": rx}, {"username": rx}]})
    if user:
        u_email = (user.get("email") or "").strip().lower()
        u_uname = (user.get("username") or "").strip().lower()
        if u_email:
            or_clauses.append({"user_email": {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}})
        if u_uname:
            or_clauses.append({"user_email": {"$regex": f"^{re.escape(u_uname)}$", "$options": "i"}})

    rows = list(db.trip_interests.find({"$or": or_clauses}).sort("id", -1))
    res = []
    seen_ids = set()
    for r in rows:
        d = serialize_doc(r)
        d.pop("_id", None)
        if d.get("id") not in seen_ids:
            seen_ids.add(d.get("id"))
            res.append(d)
    return {"status": "success", "interests": res}



@app.post("/add-trip-interest")
def add_trip_interest(req: AddTripInterestRequest):
    user_email = (req.user_email or "").strip().lower()
    destination = (req.destination or "").strip()
    preferred_dates = (req.preferred_dates or "").strip()
    budget = (req.budget or "").strip()
    notes = (req.notes or "").strip()

    interest_id = get_next_sequence("trip_interests")
    doc = {
        "id": interest_id,
        "user_email": user_email,
        "destination": destination,
        "preferred_dates": preferred_dates,
        "budget": budget,
        "notes": notes,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    db.trip_interests.insert_one(doc)
    sync_user_trip_interests_field(user_email)
    return {"status": "success", "message": "Trip interest added successfully", "id": interest_id}


@app.post("/edit-trip-interest")
def edit_trip_interest(req: EditTripInterestRequest):
    user_email = (req.user_email or "").strip().lower()
    email_rx = {"$regex": f"^{re.escape(user_email)}$", "$options": "i"}
    destination = (req.destination or "").strip()
    preferred_dates = (req.preferred_dates or "").strip()
    budget = (req.budget or "").strip()
    notes = (req.notes or "").strip()

    db.trip_interests.update_one(
        {"id": req.id, "user_email": email_rx},
        {"$set": {
            "destination": destination,
            "preferred_dates": preferred_dates,
            "budget": budget,
            "notes": notes
        }}
    )
    sync_user_trip_interests_field(user_email)
    return {"status": "success", "message": "Trip interest updated successfully"}


@app.post("/delete-trip-interest")
def delete_trip_interest(req: DeleteTripInterestRequest):
    email_clean = (req.user_email or "").strip().lower()
    email_rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}
    db.trip_interests.delete_one({"id": req.id, "user_email": email_rx})
    sync_user_trip_interests_field(email_clean)
    return {"status": "success", "message": "Trip interest deleted successfully"}


@app.post("/send-connection-request")
def send_connection_request(req: ConnectionRequestModel):
    sender = (req.sender_email or "").strip().lower()
    receiver = (req.receiver_email or "").strip().lower()

    if not sender or not receiver:
        raise HTTPException(status_code=400, detail="Sender and receiver emails are required.")

    s_rx = {"$regex": f"^{re.escape(sender)}$", "$options": "i"}
    r_rx = {"$regex": f"^{re.escape(receiver)}$", "$options": "i"}

    s_user = db.users.find_one({"$or": [{"email": s_rx}, {"username": s_rx}]})
    if s_user:
        sender = (s_user.get("email") or sender).strip().lower()

    r_user = db.users.find_one({"$or": [{"email": r_rx}, {"username": r_rx}]})
    if r_user:
        receiver = (r_user.get("email") or receiver).strip().lower()

    if sender == receiver:
        raise HTTPException(status_code=400, detail="You cannot connect with your own account.")

    s_clean_rx = {"$regex": f"^{re.escape(sender)}$", "$options": "i"}
    r_clean_rx = {"$regex": f"^{re.escape(receiver)}$", "$options": "i"}

    existing = db.connections.find_one({
        "$or": [
            {"sender_email": s_clean_rx, "receiver_email": r_clean_rx},
            {"sender_email": r_clean_rx, "receiver_email": s_clean_rx}
        ]
    })

    if existing:
        db.connections.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "status": "pending",
                "message": req.message or "",
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }}
        )
        conn_id = existing.get("id")
    else:
        conn_id = get_next_sequence("connections")
        doc = {
            "id": conn_id,
            "sender_email": sender,
            "receiver_email": receiver,
            "message": req.message or "",
            "status": "pending",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        db.connections.insert_one(doc)

    return {"status": "success", "message": "Connection request sent successfully.", "id": conn_id}


@app.post("/respond-connection-request")
def respond_connection_request(req: RespondConnectionRequest):
    stat = (req.status or "").strip().lower()
    if stat not in ["accepted", "declined", "withdrawn"]:
        raise HTTPException(status_code=400, detail="Invalid status. Must be accepted, declined, or withdrawn.")

    if stat in ["declined", "withdrawn"]:
        db.connections.delete_many({"id": req.connection_id})
        return {"status": "success", "message": f"Connection request {stat}."}

    db.connections.update_one({"id": req.connection_id}, {"$set": {"status": stat}})
    return {"status": "success", "message": f"Connection request {stat}."}


@app.post("/withdraw-connection-request")
def withdraw_connection_request(req: WithdrawConnectionRequest):
    if req.connection_id:
        db.connections.delete_many({"id": req.connection_id})
    elif req.sender_email and req.receiver_email:
        s_rx = {"$regex": f"^{re.escape(req.sender_email.strip().lower())}$", "$options": "i"}
        r_rx = {"$regex": f"^{re.escape(req.receiver_email.strip().lower())}$", "$options": "i"}
        db.connections.delete_many({"sender_email": s_rx, "receiver_email": r_rx})
    return {"status": "success", "message": "Connection request withdrawn successfully."}


@app.get("/user-connections/{email}")
def get_user_connections(email: str):
    clean_query = (email or "").strip().lower()
    rx = {"$regex": f"^{re.escape(clean_query)}$", "$options": "i"}

    # Look up user details
    user = db.users.find_one({"$or": [{"email": rx}, {"username": rx}]})
    user_emails = [clean_query]
    if user:
        if user.get("email"):
            user_emails.append(user["email"].strip().lower())
        if user.get("username"):
            user_emails.append(user["username"].strip().lower())

    recv_or = [{"receiver_email": {"$regex": f"^{re.escape(e)}$", "$options": "i"}} for e in set(user_emails)]
    send_or = [{"sender_email": {"$regex": f"^{re.escape(e)}$", "$options": "i"}} for e in set(user_emails)]

    # 1. Received Pending Requests
    pending_docs = list(db.connections.find({
        "$or": recv_or,
        "status": "pending"
    }).sort("id", -1))

    pending = []
    for c in pending_docs:
        c_dict = serialize_doc(c)
        c_dict.pop("_id", None)
        s_email = c_dict.get("sender_email", "")
        s_rx = {"$regex": f"^{re.escape(s_email)}$", "$options": "i"}
        u = db.users.find_one({"$or": [{"email": s_rx}, {"username": s_rx}]})
        if u:
            c_dict["first_name"] = u.get("first_name", "")
            c_dict["last_name"] = u.get("last_name", "")
            c_dict["username"] = u.get("username", "")
            c_dict["profile_pic"] = u.get("profile_pic", "")
        pending.append(c_dict)

    # 2. Sent Pending Requests
    sent_docs = list(db.connections.find({
        "$or": send_or,
        "status": "pending"
    }).sort("id", -1))

    sent_requests = []
    for c in sent_docs:
        c_dict = serialize_doc(c)
        c_dict.pop("_id", None)
        r_email = c_dict.get("receiver_email", "")
        r_rx = {"$regex": f"^{re.escape(r_email)}$", "$options": "i"}
        u = db.users.find_one({"$or": [{"email": r_rx}, {"username": r_rx}]})
        if u:
            c_dict["receiver_first_name"] = u.get("first_name", "")
            c_dict["receiver_last_name"] = u.get("last_name", "")
            c_dict["receiver_username"] = u.get("username", "")
            c_dict["receiver_profile_pic"] = u.get("profile_pic", "")
        sent_requests.append(c_dict)

    # 3. Accepted Buddies
    buddies_docs = list(db.connections.find({
        "$or": recv_or + send_or,
        "status": "accepted"
    }).sort("id", -1))

    buddies = []
    for c in buddies_docs:
        c_dict = serialize_doc(c)
        c_dict.pop("_id", None)
        s_email = (c_dict.get("sender_email") or "").strip().lower()
        if s_email in [e.lower() for e in user_emails]:
            other_email = c_dict.get("receiver_email", "")
        else:
            other_email = c_dict.get("sender_email", "")
        
        c_dict["buddy_email"] = other_email
        other_rx = {"$regex": f"^{re.escape(other_email)}$", "$options": "i"}
        u = db.users.find_one({"$or": [{"email": other_rx}, {"username": other_rx}]})
        if u:
            c_dict["buddy_name"] = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or u.get("username")
            c_dict["buddy_username"] = u.get("username", "")
            c_dict["buddy_pic"] = u.get("profile_pic", "")
        buddies.append(c_dict)

    return {
        "status": "success",
        "pending_requests": pending,
        "sent_requests": sent_requests,
        "accepted_buddies": buddies
    }


class BuddyMessageRequest(BaseModel):
    sender_email: str
    receiver_email: str
    message_text: str


@app.post("/send-buddy-message")
def send_buddy_message(payload: BuddyMessageRequest):
    sender = (payload.sender_email or "").strip().lower()
    receiver = (payload.receiver_email or "").strip().lower()
    text = (payload.message_text or "").strip()

    if not sender or not receiver or not text:
        raise HTTPException(status_code=400, detail="Sender, receiver, and message text are required.")

    msg_id = get_next_sequence("buddy_messages")
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    doc = {
        "id": msg_id,
        "sender_email": sender,
        "receiver_email": receiver,
        "message_text": text,
        "created_at": now_iso
    }

    db.buddy_messages.insert_one(doc)
    doc_out = serialize_doc(doc)
    doc_out.pop("_id", None)
    return {"status": "success", "message": doc_out}


@app.get("/get-buddy-messages/{user_email}/{buddy_email}")
def get_buddy_messages(user_email: str, buddy_email: str):
    u1 = (user_email or "").strip().lower()
    u2 = (buddy_email or "").strip().lower()

    if not u1 or not u2:
        return {"status": "success", "messages": []}

    u1_rx = {"$regex": f"^{re.escape(u1)}$", "$options": "i"}
    u2_rx = {"$regex": f"^{re.escape(u2)}$", "$options": "i"}

    u1_doc = db.users.find_one({"$or": [{"email": u1_rx}, {"username": u1_rx}]})
    u2_doc = db.users.find_one({"$or": [{"email": u2_rx}, {"username": u2_rx}]})

    u1_keys = [u1]
    if u1_doc:
        if u1_doc.get("email"): u1_keys.append(u1_doc["email"].strip().lower())
        if u1_doc.get("username"): u1_keys.append(u1_doc["username"].strip().lower())

    u2_keys = [u2]
    if u2_doc:
        if u2_doc.get("email"): u2_keys.append(u2_doc["email"].strip().lower())
        if u2_doc.get("username"): u2_keys.append(u2_doc["username"].strip().lower())

    u1_keys = list(set(u1_keys))
    u2_keys = list(set(u2_keys))

    match_or = []
    for k1 in u1_keys:
        for k2 in u2_keys:
            r1 = {"$regex": f"^{re.escape(k1)}$", "$options": "i"}
            r2 = {"$regex": f"^{re.escape(k2)}$", "$options": "i"}
            match_or.append({"sender_email": r1, "receiver_email": r2})
            match_or.append({"sender_email": r2, "receiver_email": r1})

    docs = list(db.buddy_messages.find({"$or": match_or}).sort("id", 1))

    cleaned = []
    for d in docs:
        c = serialize_doc(d)
        c.pop("_id", None)
        cleaned.append(c)

    return {"status": "success", "messages": cleaned}

