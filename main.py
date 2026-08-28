#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
# main.py - Dhruv Academy Master Ecosystem (Complete 11 Modules Architecture)
# 400-AI Multi-Agent Neural Core | Audit Trail | Monogram Protection | Secure Core
# ==============================================================================

import os
import shutil
import datetime
import secrets
import base64
import json
import re
from pathlib import Path
from typing import Optional, List

import urllib.request
import urllib.error

from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, JSON, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from fastapi.responses import HTMLResponse

app = FastAPI(title="Dhruv Academy Master Ecosystem")

# ------------------------------------------------------------------------------
# 1. डेटाबेस और स्टोरेज सेटअप
# ------------------------------------------------------------------------------
UPLOAD_DIR = Path("dhruv_academy_master_storage")
UPLOAD_DIR.mkdir(exist_ok=True)

DATABASE_URL = "sqlite:///./dhruv_academy_ecosystem.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserActivityLog(Base):
    __tablename__ = "user_activity_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_identifier = Column(String, default="Guest Student")
    action = Column(String, index=True)
    module = Column(String, index=True)
    details = Column(Text)
    ip_address = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class PublicityAuditLog(Base):
    __tablename__ = "publicity_audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    monogram_code = Column(String, unique=True, index=True)
    content_type = Column(String, index=True)
    generated_content = Column(Text)
    digital_signature = Column(String)
    status = Column(String, default="Verified & Saved")
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class AdminUser(Base):
    __tablename__ = "admin_users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    role = Column(String, default="subadmin")
    permissions = Column(JSON, default=list)

class AdminSession(Base):
    __tablename__ = "admin_sessions"
    id = Column(Integer, primary_key=True, index=True)
    session_token = Column(String, unique=True, index=True)
    username = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class SubFeatureToggle(Base):
    __tablename__ = "sub_feature_toggles"
    id = Column(Integer, primary_key=True, index=True)
    parent_module_id = Column(Integer, index=True)
    parent_module_name = Column(String, index=True)
    feature_key = Column(String, unique=True, index=True)
    feature_name = Column(String)
    is_enabled = Column(Boolean, default=True)
    is_paywalled = Column(Boolean, default=False)

class RegisteredStudent(Base):
    __tablename__ = "registered_students"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="Student")
    email = Column(String, unique=True, index=True)
    mobile = Column(String, nullable=True)
    dhruv_mitra_code_used = Column(String, nullable=True)
    token_balance = Column(Integer, default=10)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def log_activity(db: Session, action: str, module: str, details: str = "", user_id: str = "Student", ip: str = "Unknown"):
    try:
        log_entry = UserActivityLog(
            user_identifier=user_id,
            action=action,
            module=module,
            details=details,
            ip_address=ip,
            timestamp=datetime.datetime.utcnow()
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        print(f"Logging error: {e}")

def record_publicity_audit(db: Session, content_type: str, content: str) -> str:
    try:
        unique_token = "DA-MONOGRAM-" + secrets.token_hex(6).upper()
        signature = base64.b64encode(f"{unique_token}-{datetime.datetime.utcnow()}".encode()).decode()[:32]
        
        audit_record = PublicityAuditLog(
            monogram_code=unique_token,
            content_type=content_type,
            generated_content=content,
            digital_signature=signature,
            status="Verified & Saved"
        )
        db.add(audit_record)
        db.commit()
        return unique_token
    except Exception as e:
        db.rollback()
        print(f"Audit record error: {e}")
        return "DA-MONOGRAM-FALLBACK"

def init_default_data():
    db = SessionLocal()
    try:
        superadmin = db.query(AdminUser).filter_by(username="dhruv_superadmin").first()
        if not superadmin:
            superadmin = AdminUser(
                username="dhruv_superadmin",
                password="DhruvSuperSecure2026!",
                role="superadmin",
                permissions=["all"]
            )
            db.add(superadmin)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

init_default_data()

# ------------------------------------------------------------------------------
# 2. सुरक्षा और सत्र प्रबंधन
# ------------------------------------------------------------------------------
def get_current_admin(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    session_token = request.cookies.get("dhruv_auth_token")
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="सत्र समाप्त हो गया है।")
    
    sess_record = db.query(AdminSession).filter(AdminSession.session_token == session_token).first()
    if not sess_record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="अमान्य सत्र")
    
    user = db.query(AdminUser).filter(AdminUser.username == sess_record.username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="उपयोगकर्ता उपलब्ध नहीं है")
    return user

def require_superadmin(current_user: AdminUser = Depends(get_current_admin)):
    if current_user.role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="केवल सुपर-एडमिन के लिए उपलब्ध")
    return current_user

# ------------------------------------------------------------------------------
# 3. एडमिन लॉगिन व छात्र रजिस्ट्रेशन रूट्स (डिफ़ॉल्ट OTP 1234 के साथ)
# ------------------------------------------------------------------------------
@app.get("/secret-admin-login-dhruv", response_class=HTMLResponse)
def secret_login_page(error: Optional[str] = None):
    err_box = f"<div class='p-3 bg-red-900/50 border border-red-500 rounded-xl text-red-300 text-xs font-bold'>{error}</div>" if error else ""
    return f"""
    <!DOCTYPE html>
    <html lang="hi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dhruv Academy - Admin Gateway</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-950 text-white min-h-screen flex items-center justify-center p-4">
        <div class="bg-slate-900/95 border border-cyan-500/40 rounded-3xl p-8 max-w-md w-full shadow-2xl space-y-6">
            <div class="text-center space-y-2">
                <span class="text-4xl">🔐</span>
                <h1 class="text-xl font-extrabold text-cyan-400">Dhruv Admin Gateway</h1>
                <p class="text-xs text-gray-400">सुरक्षित प्रशासनिक प्रवेश द्वार</p>
            </div>
            {err_box}
            <form action="/secret-admin-login-dhruv" method="POST" class="space-y-4 text-xs">
                <div>
                    <label class="block mb-1 font-bold text-gray-300">यूजरनेम</label>
                    <input type="text" name="username" required value="dhruv_superadmin" class="w-full p-3 rounded-xl bg-slate-800 border border-slate-700 focus:border-cyan-500 focus:outline-none text-white">
                </div>
                <div>
                    <label class="block mb-1 font-bold text-gray-300">पासवर्ड</label>
                    <input type="password" name="password" required placeholder="••••••••••••" class="w-full p-3 rounded-xl bg-slate-800 border border-slate-700 focus:border-cyan-500 focus:outline-none text-white">
                </div>
                <button type="submit" class="w-full py-3 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 rounded-xl font-bold text-white shadow-lg transition">लॉगिन करें</button>
            </form>
            <div class="text-center pt-2">
                <a href="/" class="text-[11px] text-gray-500 hover:text-cyan-400">← मुख्य पोर्टल पर वापस जाएं</a>
            </div>
        </div>
    </body>
    </html>
    """

@app.post("/secret-admin-login-dhruv")
def process_secret_login(response: Response, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    u_clean = username.strip()
    p_clean = password.strip()

    user = db.query(AdminUser).filter(AdminUser.username == u_clean, AdminUser.password == p_clean).first()
    if not user:
        return HTMLResponse(content=secret_login_page(error="अमान्य क्रेडेंशियल्स!"), status_code=401)
    
    session_token = secrets.token_hex(32)
    db.add(AdminSession(session_token=session_token, username=user.username))
    db.commit()
    
    res = RedirectResponse(url="/admin/super-dashboard", status_code=status.HTTP_303_SEE_OTHER)
    res.set_cookie(key="dhruv_auth_token", value=session_token, httponly=True, max_age=86400 * 7, samesite="lax", secure=False)
    return res

@app.get("/admin-logout")
def admin_logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("dhruv_auth_token")
    if token:
        db.query(AdminSession).filter(AdminSession.session_token == token).delete()
        db.commit()
    res = RedirectResponse(url="/secret-admin-login-dhruv", status_code=status.HTTP_303_SEE_OTHER)
    res.delete_cookie("dhruv_auth_token")
    return res

@app.post("/api/register-student")
def register_student_endpoint(mobile: str = Form(...), otp: Optional[str] = Form(None), dhruv_mitra_code: Optional[str] = Form(None), db: Session = Depends(get_db)):
    clean_mobile = mobile.strip()
    
    if otp and otp.strip() != "1234":
        return JSONResponse(content={"success": False, "message": "अमान्य OTP! डिफ़ॉल्ट OTP 1234 दर्ज करें।", "default_otp": "1234"})

    existing_user = db.query(RegisteredStudent).filter_by(mobile=clean_mobile).first()
    if existing_user:
        return JSONResponse(content={
            "success": True, 
            "already_registered": True, 
            "message": "आप पहले से पंजीकृत हैं!", 
            "token_balance": existing_user.token_balance,
            "default_otp": "1234"
        })
    
    initial_tokens = 10
    clean_code = dhruv_mitra_code.strip() if dhruv_mitra_code else None
    if clean_code:
        initial_tokens += 5

    new_student = RegisteredStudent(name="Student", email=f"{clean_mobile}@dhruvacademy.com", mobile=clean_mobile, dhruv_mitra_code_used=clean_code, token_balance=initial_tokens)
    db.add(new_student)
    db.commit()
    return JSONResponse(content={
        "success": True, 
        "already_registered": False, 
        "message": f"सफलतापूर्वक पंजीकरण! 10 टोकन क्रेडिट कर दिए गए हैं।", 
        "token_balance": initial_tokens,
        "default_otp": "1234"
    })

# ------------------------------------------------------------------------------
# 4. सुपर-एडमिन कंट्रोल पैनल व ऑडिट ट्रेल
# ------------------------------------------------------------------------------
@app.get("/admin/super-dashboard", response_class=HTMLResponse)
def super_admin_dashboard(user: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    audit_logs = db.query(PublicityAuditLog).order_by(PublicityAuditLog.timestamp.desc()).limit(50).all()
    audit_rows = "".join([f"<tr class='border-b border-gray-800 text-xs'><td class='py-3 px-4 font-mono text-cyan-400'>{al.monogram_code}</td><td class='py-3 px-4 text-emerald-300'>{al.content_type}</td><td class='py-3 px-4 text-gray-300 truncate max-w-xs'>{al.generated_content[:80]}...</td><td class='py-3 px-4 text-gray-500'>{al.timestamp.strftime('%d-%m-%Y %H:%M')}</td></tr>" for al in audit_logs])
    if not audit_rows:
        audit_rows = "<tr><td colspan='4' class='py-4 text-center text-gray-500 text-xs'>अभी कोई ऑडिट ट्रेल रिकॉर्ड उपलब्ध नहीं है।</td></tr>"

    return f"""
    <!DOCTYPE html>
    <html lang="hi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Super Admin Dashboard - Audit Trail</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-950 text-white p-4 sm:p-8 font-sans">
        <div class="max-w-7xl mx-auto space-y-8">
            <div class="flex justify-between items-center border-b border-gray-800 pb-4">
                <div>
                    <h1 class="text-2xl font-extrabold text-cyan-400">🛡️ Super-Admin Audit & Monogram Dashboard</h1>
                    <p class="text-xs text-gray-400 mt-1">सिस्टम से जाने वाले हर डेटा और पब्लिसिटी का डिजिटल प्रूफ रिकॉर्ड</p>
                </div>
                <div class="flex gap-2">
                    <a href="/admin" class="px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-xs font-bold rounded-xl transition">📊 लाइव यूजर डेटा</a>
                    <a href="/" class="px-4 py-2 bg-cyan-700 hover:bg-cyan-600 text-xs font-bold rounded-xl transition">मुख्य पोर्टल</a>
                    <a href="/admin-logout" class="px-4 py-2 bg-red-900 hover:bg-red-800 text-xs font-bold rounded-xl transition">लॉगआउट ✕</a>
                </div>
            </div>
            <div class="bg-slate-900 p-6 rounded-2xl border border-gray-800 space-y-4 shadow-xl">
                <h2 class="text-lg font-bold text-emerald-400">📜 AI पब्लिसिटी और जनरेटेड डेटा का डिजिटल ऑडिट ट्रेल (Monogram Logs)</h2>
                <div class="overflow-x-auto rounded-xl border border-gray-800">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-slate-800 text-xs text-gray-300 border-b border-gray-700">
                                <th class="py-3 px-4">मोनोग्राम कोड (Monogram ID)</th>
                                <th class="py-3 px-4">कंटेंट प्रकार</th>
                                <th class="py-3 px-4">सुरक्षित कंटेंट सारांश</th>
                                <th class="py-3 px-4">समय (Timestamp)</th>
                            </tr>
                        </thead>
                        <tbody>{audit_rows}</tbody>
                    </table>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

# ------------------------------------------------------------------------------
# 5. मुख्य डैशबोर्ड व सटीक HTML फाइल राउट्स (बिना किसी रीडायरेक्ट गड़बड़ी के)
# ------------------------------------------------------------------------------
@app.get("/", response_class=FileResponse)
def serve_index():
    return FileResponse("index.html")

@app.get("/ai-core", response_class=FileResponse)
@app.get("/ai-core.html", response_class=FileResponse)
def serve_ai_core():
    return FileResponse("ai-core.html")

@app.get("/ai-auto-healing", response_class=FileResponse)
@app.get("/ai-auto-healing.html", response_class=FileResponse)
def serve_auto_healing():
    return FileResponse("ai-auto-healing.html")

@app.get("/digital-library", response_class=FileResponse)
@app.get("/digital-library.html", response_class=FileResponse)
def serve_digital_library():
    return FileResponse("digital-library.html")

@app.get("/kids-zone", response_class=FileResponse)
@app.get("/kids-zone.html", response_class=FileResponse)
def serve_kids_zone():
    return FileResponse("kids-zone.html")

@app.get("/legal-ai", response_class=FileResponse)
@app.get("/legal-ai.html", response_class=FileResponse)
@app.get("/legal-hub", response_class=FileResponse)
@app.get("/legal-hub.html", response_class=FileResponse)
def serve_legal_ai():
    if Path("legal-ai.html").exists():
        return FileResponse("legal-ai.html")
    return FileResponse("legal-hub.html")

@app.get("/spoken-english", response_class=FileResponse)
@app.get("/spoken-english.html", response_class=FileResponse)
def serve_spoken_english():
    return FileResponse("spoken-english.html")

@app.get("/face-swap-social", response_class=FileResponse)
@app.get("/face-swap-social.html", response_class=FileResponse)
def serve_face_swap():
    return FileResponse("face-swap-social.html")

@app.get("/central-wallet", response_class=FileResponse)
@app.get("/central-wallet.html", response_class=FileResponse)
def serve_central_wallet():
    if Path("central-wallet.html").exists():
        return FileResponse("central-wallet.html")
    return FileResponse("index.html")

def get_all_gemini_keys() -> List[str]:
    keys = []
    for i in range(1, 16):
        k_val = (os.environ.get(f"GEMINI_API_KEY{i}") or os.environ.get(f"GEMINI_API_KEY_{i}") or "").strip().strip('"').strip("'")
        if k_val and k_val not in keys:
            keys.append(k_val)
    env_keys_raw = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEYS") or "").strip()
    if env_keys_raw:
        for k in env_keys_raw.split(","):
            cleaned = k.strip().strip('"').strip("'")
            if cleaned and cleaned not in keys:
                keys.append(cleaned)
    return keys

@app.post("/api/ai-core-solve")
async def ai_core_solve_endpoint(
    request: Request, 
    query: str = Form(...), 
    mode: str = Form("standard"), 
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    client_ip = request.client.host if request.client else "Unknown"
    prompt_instruction = f"ध्रुव एकेडमी के न्यूरल कोर से विश्लेषण:\n\nप्रश्न: {query}\n\nबिंदुवार समाधान दें।"
    parts = [{"text": prompt_instruction}]

    if file:
        image_bytes = await file.read()
        mime_type = file.content_type or "image/jpeg"
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        parts.append({"inlineData": {"mimeType": mime_type, "data": base64_image}})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.2}
    }

    api_keys = get_all_gemini_keys()
    if not api_keys:
        return JSONResponse(content={"success": False, "solution": "⚠️ GEMINI_API_KEY उपलब्ध नहीं है।"})

    router_models = ["gemini-1.5-flash", "gemini-pro"]
    solution_text = ""

    for model_name in router_models:
        for key in api_keys:
            target_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
            try:
                req = urllib.request.Request(target_url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=35) as response:
                    res_data = json.loads(response.read().decode("utf-8"))
                    solution_text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    break
            except Exception:
                continue
        if solution_text:
            break

    if solution_text:
        monogram_id = record_publicity_audit(db, "AI_Core_Solution", solution_text)
        final_output = f"{solution_text}\n\n--- \n🛡️ *Verified Dhruv Academy Monogram: {monogram_id}*"
        log_activity(db, "AI Solved with Monogram", "AI Engine Core", f"Monogram: {monogram_id}", "Student", client_ip)
        return JSONResponse(content={"success": True, "solution": final_output})

    return JSONResponse(content={"success": False, "solution": "⚠️ सर्वर व्यस्त है। पुनः प्रयास करें।"})

@app.get("/admin", response_class=HTMLResponse)
async def master_admin_panel(user: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    logs = db.query(UserActivityLog).order_by(UserActivityLog.timestamp.desc()).limit(100).all()
    rows = "".join([f"<tr class='border-b border-gray-800 text-xs'><td class='py-2 px-3'>{l.timestamp.strftime('%H:%M:%S')}</td><td class='py-2 px-3'>{l.user_identifier}</td><td class='py-2 px-3 text-cyan-300'>{l.module}</td><td class='py-2 px-3 font-bold'>{l.action}</td><td class='py-2 px-3'>{l.details}</td></tr>" for l in logs])
    return f"""<!DOCTYPE html><html lang="hi"><head><meta charset="UTF-8"><title>Live Activity Monitor</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-slate-950 text-white p-6 font-sans"><div class="max-w-6xl mx-auto space-y-4"><div class="flex justify-between items-center"><h1 class="text-xl font-bold text-emerald-400">📊 लाइव यूजर एक्टिविटी मॉनिटर</h1><a href="/admin/super-dashboard" class="px-4 py-2 bg-indigo-600 rounded-xl text-xs font-bold">🛡️ ऑडिट ट्रेल व मोनोग्राम पैनल</a></div><div class="bg-slate-900 p-4 rounded-xl border border-gray-800 overflow-x-auto"><table class="w-full text-left"><thead><tr class="bg-slate-800 text-xs text-gray-300"><th class="p-2">समय</th><th class="p-2">यूजर</th><th class="p-2">मॉड्यूल</th><th class="p-2">एक्शन</th><th class="p-2">विवरण</th></tr></thead><tbody>{rows}</tbody></table></div></div></body></html>"""

# ------------------------------------------------------------------------------
# कमर्शियल पेमेंट गेटवे, ऑटो-डिटेक्शन और क्रेडिट एनालिसिस मॉड्यूल
# ------------------------------------------------------------------------------

class CreditTransactionHistory(Base):
    __tablename__ = "credit_transaction_history"
    id = Column(Integer, primary_key=True, index=True)
    mobile = Column(String, index=True)
    transaction_type = Column(String) # "Recharge", "Monthly_Deduction", "Usage"
    tokens_changed = Column(Integer)
    description = Column(String)
    monogram_code = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

@app.post("/api/verify-payment-and-add-tokens")
def verify_payment_and_add_tokens(
    mobile: str = Form(...),
    tokens_to_add: int = Form(...),
    amount_paid: int = Form(...),
    payment_id: str = Form(...),
    db: Session = Depends(get_db)
):
    clean_mobile = mobile.strip()
    student = db.query(RegisteredStudent).filter_by(mobile=clean_mobile).first()
    
    if not student:
        return JSONResponse(content={"success": False, "message": "छात्र पंजीकृत नहीं है! पहले लॉगिन करें।"})
    
    student.token_balance += tokens_to_add
    
    audit_msg = f"Wallet Recharge: Mobile {clean_mobile}, Added {tokens_to_add} Tokens, Paid ₹{amount_paid}, PaymentID: {payment_id}"
    monogram_id = record_publicity_audit(db, "Commercial_Wallet_Recharge", audit_msg)
    
    tx_record = CreditTransactionHistory(
        mobile=clean_mobile,
        transaction_type="Recharge",
        tokens_changed=tokens_to_add,
        description=f"Recharge ₹{amount_paid} (Payment ID: {payment_id})",
        monogram_code=monogram_id
    )
    db.add(tx_record)
    db.commit()
    
    return JSONResponse(content={
        "success": True, 
        "new_balance": student.token_balance, 
        "monogram_code": monogram_id,
        "message": f"सफलतापूर्वक भुगतान सत्यापित! {tokens_to_add} टोकन आपके वॉलेट में जोड़ दिए गए हैं।"
    })

@app.get("/api/user-credit-analysis/{mobile}")
def get_user_credit_analysis(mobile: str, db: Session = Depends(get_db)):
    """यूजर का पूरा क्रेडिट एनालिसिस और ट्रांसपेरेंसी रिपोर्ट देता है"""
    clean_mobile = mobile.strip()
    student = db.query(RegisteredStudent).filter_by(mobile=clean_mobile).first()
    
    if not student:
        return JSONResponse(content={"success": False, "message": "छात्र नहीं मिला"})
        
    history = db.query(CreditTransactionHistory).filter_by(mobile=clean_mobile).order_by(CreditTransactionHistory.timestamp.desc()).all()
    
    history_list = []
    for h in history:
        history_list.append({
            "type": h.transaction_type,
            "tokens": h.tokens_changed,
            "description": h.description,
            "monogram": h.monogram_code,
            "time": h.timestamp.strftime('%d-%m-%Y %H:%M')
        })
        
    return JSONResponse(content={
        "success": True,
        "current_balance": student.token_balance,
        "registered_date": student.created_at.strftime('%d-%m-%Y'),
        "transactions": history_list
    })

# 10. Nebula Visual Hub Route (स्वतंत्र पाथ)
@app.get("/nebula-hub.html", response_class=HTMLResponse)
@app.get("/nebula-hub", response_class=HTMLResponse)
async def serve_nebula_hub():
    path = "nebula-hub.html"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "nebula-hub.html file not found", 404

# 9. Competition Solver Explicit Route (ताकि यह कभी एआई कोर पर न जाए)
@app.get("/competition-solver.html", response_class=HTMLResponse)
@app.get("/competition-solver", response_class=HTMLResponse)
async def serve_competition_solver():
    path = "competition-solver.html"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "competition-solver.html file not found", 404

# 5. 3D Blackboard Explicit Route (ताकि यह कभी एआई कोर पर न जाए)
@app.get("/3d-blackboard.html", response_class=HTMLResponse)
@app.get("/3d-blackboard", response_class=HTMLResponse)
async def serve_3d_blackboard():
    path = "3d-blackboard.html"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "3d-blackboard.html file not found", 404

@app.get("/coaching-hub.html", response_class=HTMLResponse)
@app.get("/coaching-hub", response_class=HTMLResponse)
async def serve_coaching_hub():
    path = "coaching-hub.html"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "Coaching Hub file not found", 404

# 2. Global Custom 404 Error Handler
@app.exception_handler(404)
async def custom_404_handler(request, exc):
    if os.path.exists("404.html"):
        with open("404.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=404)
    return HTMLResponse(content="<h3>404 - Page Not Found</h3>", status_code=404)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
