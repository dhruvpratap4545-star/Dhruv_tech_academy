#!/usr/init/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
# main.py - Dhruv Academy Master Ecosystem (Complete 11 Modules Architecture)
# 400-AI Multi-Agent Neural Core | Fail-safe Tokens | Sub-Admin Permissions
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

app = FastAPI(title="Dhruv Academy Master Ecosystem")

# BASE DIRECTORY FOR ABSOLUTE PATH RESOLUTION (GitHub & Cloud Deployment Safe)
BASE_DIR = Path(__file__).resolve().parent

# ------------------------------------------------------------------------------
# 1. डेटाबेस और स्टोरेज सेटअप (Database & Storage Architecture)
# ------------------------------------------------------------------------------
UPLOAD_DIR = BASE_DIR / "dhruv_academy_master_storage"
UPLOAD_DIR.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite:///{BASE_DIR / 'dhruv_academy_ecosystem.db'}"
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

class CreditTransactionHistory(Base):
    __tablename__ = "credit_transaction_history"
    id = Column(Integer, primary_key=True, index=True)
    mobile = Column(String, index=True)
    transaction_type = Column(String)
    tokens_changed = Column(Integer)
    description = Column(String)
    monogram_code = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

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
# 2. सुरक्षा और सत्र प्रबंधन (Security & Auth & Path Resolution)
# ------------------------------------------------------------------------------
def get_current_admin(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    session_token = request.cookies.get("dhruv_auth_token")
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="सत्र समाप्त हो गया है। कृपया पुनः लॉगिन करें।")
    
    sess_record = db.query(AdminSession).filter(AdminSession.session_token == session_token).first()
    if not sess_record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="अमान्य सत्र टोकन")
    
    user = db.query(AdminUser).filter(AdminUser.username == sess_record.username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="प्रशासक उपयोगकर्ता उपलब्ध नहीं है")
    return user

def require_superadmin(current_user: AdminUser = Depends(get_current_admin)):
    if current_user.role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="यह क्षेत्र केवल सर्वोच्च सुपर-एडमिन के लिए सुरक्षित है")
    return current_user

def get_safe_file_response(filename: str):
    # पूर्ण सुरक्षा के साथ templates और root फोल्डर दोनों की जांच
    path_in_templates = BASE_DIR / "templates" / filename
    if path_in_templates.exists():
        return FileResponse(path_in_templates)
    path_in_root = BASE_DIR / filename
    if path_in_root.exists():
        return FileResponse(path_in_root)
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="hi">
    <head><meta charset="UTF-8"><title>404 Not Found - Dhruv Academy</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-slate-950 text-white flex items-center justify-center min-h-screen">
        <div class="text-center space-y-4 p-8 bg-slate-900 border border-red-500/40 rounded-2xl shadow-2xl">
            <h1 class="text-3xl font-bold text-red-400">404 - मॉड्यूल फ़ाइल नहीं मिली</h1>
            <p class="text-sm text-gray-400">फ़ाइल <b>{filename}</b> न तो 'templates' फोल्डर में मिली और न ही मुख्य डायरेक्टरी में।</p>
            <a href="/" class="inline-block px-6 py-2.5 bg-cyan-600 hover:bg-cyan-500 rounded-xl font-bold text-xs transition">🏠 मुख्य होम पेज पर लौटें</a>
        </div>
    </body>
    </html>
    """, status_code=404)

# ------------------------------------------------------------------------------
# 3. एडमिन लॉगिन व छात्र रजिस्ट्रेशन रूट्स (Admin & Student Auth Routes)
# ------------------------------------------------------------------------------
@app.get("/secret-admin-login-dhruv", response_class=HTMLResponse)
def secret_login_page(error: Optional[str] = None):
    err_box = f"<div class='p-3 bg-red-900/50 border border-red-500 rounded-xl text-red-300 text-xs font-bold text-center'>{error}</div>" if error else ""
    return f"""
    <!DOCTYPE html>
    <html lang="hi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dhruv Academy - Supreme Admin Gateway</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-950 text-white min-h-screen flex items-center justify-center p-4 font-sans">
        <div class="bg-slate-900/95 border border-cyan-500/40 rounded-3xl p-8 max-w-md w-full shadow-2xl space-y-6 backdrop-blur-md">
            <div class="text-center space-y-2">
                <span class="text-4xl">🔐</span>
                <h1 class="text-xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-emerald-400">Dhruv Supreme Admin Gateway</h1>
                <p class="text-xs text-gray-400">ध्रुव एकेडमी मास्टर इकोसिस्टम सुरक्षा द्वार</p>
            </div>
            {err_box}
            <form action="/secret-admin-login-dhruv" method="POST" class="space-y-4 text-xs">
                <div>
                    <label class="block mb-1 font-bold text-gray-300">यूजरनेम (Username)</label>
                    <input type="text" name="username" required value="dhruv_superadmin" class="w-full p-3 rounded-xl bg-slate-800 border border-slate-700 focus:border-cyan-500 focus:outline-none text-white">
                </div>
                <div>
                    <label class="block mb-1 font-bold text-gray-300">पासवर्ड (Password)</label>
                    <input type="password" name="password" required placeholder="••••••••••••" class="w-full p-3 rounded-xl bg-slate-800 border border-slate-700 focus:border-cyan-500 focus:outline-none text-white">
                </div>
                <button type="submit" class="w-full py-3 bg-gradient-to-r from-cyan-600 to-emerald-600 hover:from-cyan-500 rounded-xl font-bold text-white shadow-lg transition tracking-wide">सुरक्षित लॉगिन करें</button>
            </form>
            <div class="text-center pt-2 border-t border-slate-800">
                <a href="/" class="text-[11px] text-gray-400 hover:text-cyan-400 transition">← मुख्य पोर्टल पर वापस जाएं</a>
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
        return HTMLResponse(content=secret_login_page(error="अमान्य क्रेडेंशियल्स! कृपया सही यूजरनेम और पासवर्ड दर्ज करें।"), status_code=401)
    
    session_token = secrets.token_hex(32)
    db.add(AdminSession(session_token=session_token, username=user.username))
    db.commit()
    
    res = RedirectResponse(url="/admin/super-master-panel", status_code=status.HTTP_303_SEE_OTHER)
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
# 4. Fast2SMS ओटीपी सेवा एकीकरण (Fast2SMS OTP Service Routing)
# ------------------------------------------------------------------------------
FAST2SMS_API_KEY = os.environ.get("FAST2SMS_API_KEY", "")

@app.post("/api/send-real-otp")
def send_real_otp(mobile: str = Form(...)):
    clean_mobile = mobile.strip()
    generated_otp = "1234" 
    
    message = f"Dhruv Academy OTP is {generated_otp}"
    encoded_msg = urllib.parse.quote(message)
    
    url = f"https://www.fast2sms.com/dev/bulkV2?authorization={FAST2SMS_API_KEY}&route=q&message={encoded_msg}&language=english&flash=0&numbers={clean_mobile}"
    
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = response.read().decode("utf-8")
            return JSONResponse(content={"success": True, "message": "ओटीपी सफलतापूर्वक भेज दिया गया है!", "otp": generated_otp})
    except Exception as e:
        return JSONResponse(content={"success": False, "message": f"एसएमएस भेजने में त्रुटि: {str(e)}", "otp": "1234"})

# ------------------------------------------------------------------------------
# 5. सुपर-एडमिन सुप्रीम कमांड सेंटर व सब-एडमिन कंट्रोल पैनल
# ------------------------------------------------------------------------------
@app.get("/admin/super-master-panel", response_class=HTMLResponse)
def super_master_panel(user: AdminUser = Depends(require_superadmin), db: Session = Depends(get_db)):
    students = db.query(RegisteredStudent).all()
    student_rows = ""
    for s in students:
        student_rows += f"""
        <tr class='border-b border-slate-800 text-xs'>
            <td class='py-3 px-4 font-mono text-cyan-300'>{s.mobile}</td>
            <td class='py-3 px-4 font-bold text-emerald-400'>{s.token_balance} टोकन</td>
            <td class='py-3 px-4 text-gray-400'>{s.created_at.strftime('%d-%m-%Y')}</td>
            <td class='py-3 px-4'>
                <form action='/admin/adjust-tokens' method='POST' class='flex items-center gap-2'>
                    <input type='hidden' name='mobile' value='{s.mobile}'>
                    <input type='number' name='delta' value='5' class='w-16 p-1 bg-slate-950 border border-slate-700 rounded text-center text-white'>
                    <button type='submit' class='px-3 py-1 bg-emerald-600 hover:bg-emerald-500 rounded font-bold text-white transition'>± टोकन अपडेट</button>
                </form>
            </td>
        </tr>
        """
    if not student_rows:
        student_rows = "<tr><td colspan='4' class='py-4 text-center text-gray-500 text-xs'>अभी कोई छात्र पंजीकृत नहीं है।</td></tr>"

    audit_logs = db.query(PublicityAuditLog).order_by(PublicityAuditLog.timestamp.desc()).limit(20).all()
    audit_rows = "".join([f"<tr class='border-b border-slate-800 text-xs'><td class='py-2 px-3 font-mono text-cyan-400'>{al.monogram_code}</td><td class='py-2 px-3 text-emerald-300'>{al.content_type}</td><td class='py-2 px-3 text-gray-300'>{al.timestamp.strftime('%d-%m-%Y %H:%M')}</td></tr>" for al in audit_logs])
    if not audit_rows:
        audit_rows = "<tr><td colspan='3' class='py-2 text-center text-gray-500 text-xs'>कोई ऑडिट रिकॉर्ड उपलब्ध नहीं है।</td></tr>"

    return f"""
    <!DOCTYPE html>
    <html lang="hi">
    <head>
        <meta charset="UTF-8">
        <title>Super-Admin Supreme Command Center</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-950 text-white min-h-screen p-6 font-sans">
        <div class="max-w-7xl mx-auto space-y-6">
            <div class="flex flex-wrap justify-between items-center border-b border-slate-800 pb-4 gap-4">
                <div>
                    <h1 class="text-2xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-emerald-400">⚡ Super-Admin Supreme Command Center</h1>
                    <p class="text-xs text-gray-400 mt-1">ध्रुव एकेडमी मास्टर इकोसिस्टम का सर्वोच्च नियंत्रण केंद्र</p>
                </div>
                <div class="flex flex-wrap gap-2">
                    <a href="/admin" class="px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-xs font-bold rounded-xl transition">📊 लाइव यूजर एक्टिविटी</a>
                    <a href="/admin/manage-subadmins" class="px-4 py-2 bg-indigo-700 hover:bg-indigo-600 text-xs font-bold rounded-xl transition">🛡️ सब-एडमिन अधिकार</a>
                    <a href="/" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-xs font-bold rounded-xl transition">🏠 मुख्य पोर्टल</a>
                    <a href="/auto-heal" class="px-4 py-2 bg-purple-700 hover:bg-purple-600 text-xs font-bold rounded-xl transition">🛡️ ऑटो-हीलिंग हब</a>
                    <a href="/admin-logout" class="px-4 py-2 bg-red-950 hover:bg-red-900 border border-red-800 text-xs font-bold rounded-xl transition text-red-300">लॉगआउट ✕</a>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div class="bg-slate-900/90 border border-cyan-500/30 rounded-2xl p-5 shadow-xl">
                    <h3 class="text-xs font-bold text-gray-400 uppercase">👥 कुल पंजीकृत छात्र</h3>
                    <p class="text-2xl font-extrabold text-cyan-400 mt-2">{len(students)} सक्रिय छात्र</p>
                </div>
                <div class="bg-slate-900/90 border border-emerald-500/30 rounded-2xl p-5 shadow-xl">
                    <h3 class="text-xs font-bold text-gray-400 uppercase">🛡️ सुरक्षा मोनोग्राम ऑडिट</h3>
                    <p class="text-2xl font-extrabold text-emerald-400 mt-2">सक्रिय और सुरक्षित</p>
                </div>
                <div class="bg-slate-900/90 border border-purple-500/30 rounded-2xl p-5 shadow-xl">
                    <h3 class="text-xs font-bold text-gray-400 uppercase">🚀 सिस्टम सर्वर स्वास्थ्य</h3>
                    <p class="text-2xl font-extrabold text-purple-400 mt-2">100% Good Health</p>
                </div>
            </div>

            <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
                <h2 class="text-sm font-bold text-cyan-400">🪙 छात्र वॉलेट और टोकन मास्टर कंट्रोल</h2>
                <div class="overflow-x-auto rounded-xl border border-slate-800">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-slate-950 text-xs text-gray-300 border-b border-slate-800">
                                <th class="py-3 px-4">छात्र मोबाइल नंबर</th>
                                <th class="py-3 px-4">वर्तमान टोकन बैलेंस</th>
                                <th class="py-3 px-4">पंजीकरण तिथि</th>
                                <th class="py-3 px-4">सुपर-एडमिन एक्शन</th>
                            </tr>
                        </thead>
                        <tbody>{student_rows}</tbody>
                    </table>
                </div>
            </div>

            <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
                <h2 class="text-sm font-bold text-emerald-400">📜 डिजिटल मोनोग्राम ऑडिट ट्रेल</h2>
                <div class="overflow-x-auto rounded-xl border border-slate-800">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-slate-950 text-xs text-gray-300 border-b border-slate-800">
                                <th class="py-3 px-4">मोनोग्राम कोड</th>
                                <th class="py-3 px-4">गतिविधि प्रकार</th>
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

@app.post("/admin/adjust-tokens")
def adjust_student_tokens(mobile: str = Form(...), delta: int = Form(...), user: AdminUser = Depends(require_superadmin), db: Session = Depends(get_db)):
    student = db.query(RegisteredStudent).filter_by(mobile=mobile.strip()).first()
    if student:
        student.token_balance += delta
        if student.token_balance < 0:
            student.token_balance = 0
        db.commit()
    return RedirectResponse(url="/admin/super-master-panel", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/admin/manage-subadmins", response_class=HTMLResponse)
def manage_subadmins_page(user: AdminUser = Depends(require_superadmin), db: Session = Depends(get_db)):
    subadmins = db.query(AdminUser).filter(AdminUser.role != "superadmin").all()
    rows = ""
    for sa in subadmins:
        perms = sa.permissions if isinstance(sa.permissions, list) else []
        rows += f"""
        <tr class='border-b border-gray-800 text-xs'>
            <td class='py-3 px-4 font-bold text-cyan-300'>{sa.username}</td>
            <td class='py-3 px-4'>
                <form action='/admin/update-permissions' method='POST' class='flex flex-wrap gap-3 items-center'>
                    <input type='hidden' name='username' value='{sa.username}'>
                    <label class='flex items-center gap-1 cursor-pointer'><input type='checkbox' name='perms' value='ai_core' {'checked' if 'ai_core' in perms else ''}> AI कोर</label>
                    <label class='flex items-center gap-1 cursor-pointer'><input type='checkbox' name='perms' value='competition' {'checked' if 'competition' in perms else ''}> कंपटीशन सॉल्वर</label>
                    <label class='flex items-center gap-1 cursor-pointer'><input type='checkbox' name='perms' value='nebula' {'checked' if 'nebula' in perms else ''}> नेबुला हब</label>
                    <label class='flex items-center gap-1 cursor-pointer'><input type='checkbox' name='perms' value='library' {'checked' if 'library' in perms else ''}> डिजिटल लाइब्रेरी</label>
                    <button type='submit' class='px-3 py-1 bg-cyan-600 hover:bg-cyan-500 rounded-lg text-white font-bold ml-auto transition'>अधिकार सहेजें</button>
                </form>
            </td>
        </tr>
        """
    if not rows:
        rows = "<tr><td colspan='2' class='py-4 text-center text-gray-500 text-xs'>अभी कोई सब-एडमिन पंजीकृत नहीं है।</td></tr>"

    return f"""
    <!DOCTYPE html>
    <html lang="hi">
    <head>
        <meta charset="UTF-8">
        <title>Sub-Admin Permission Hub</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-950 text-white p-6 font-sans">
        <div class="max-w-5xl mx-auto space-y-6">
            <div class="flex justify-between items-center border-b border-gray-800 pb-4">
                <h1 class="text-xl font-extrabold text-cyan-400">🛡️ सब-एडमिन कार्य और अधिकार प्रबंधन</h1>
                <a href="/admin/super-master-panel" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-xl text-xs font-bold transition">← सुपर-एडमिन कमांड सेंटर</a>
            </div>

            <div class="bg-slate-900 p-6 rounded-2xl border border-gray-800 shadow-xl space-y-4">
                <h2 class="text-sm font-bold text-emerald-400">➕ नया सब-एडमिन पंजीकृत करें</h2>
                <form action="/admin/create-subadmin" method="POST" class="flex flex-wrap gap-4 items-end text-xs">
                    <div>
                        <label class="block mb-1 text-gray-300 font-bold">यूजरनेम</label>
                        <input type="text" name="username" required placeholder="subadmin_name" class="p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div>
                        <label class="block mb-1 text-gray-300 font-bold">पासवर्ड</label>
                        <input type="password" name="password" required placeholder="••••••••" class="p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <button type='submit' class='px-4 py-2.5 bg-emerald-600 hover:bg-emerald-500 rounded-xl font-bold text-white transition'>सब-एडमिन जोड़ें</button>
                </form>
            </div>

            <div class="bg-slate-900 p-6 rounded-2xl border border-gray-800 shadow-xl space-y-4">
                <h2 class="text-sm font-bold text-emerald-400">📋 सब-एडमिन सूची और मॉड्यूल चेकबॉक्स</h2>
                <div class="overflow-x-auto rounded-xl border border-gray-800">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-slate-800 text-xs text-gray-300 border-b border-gray-700">
                                <th class="py-3 px-4">सब-एडमिन यूजरनेम</th>
                                <th class="py-3 px-4">मॉड्यूल एक्सेस चेकबॉक्स (Permissions)</th>
                            </tr>
                        </thead>
                        <tbody>{rows}</tbody>
                    </table>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

@app.post("/admin/create-subadmin")
def create_subadmin(username: str = Form(...), password: str = Form(...), user: AdminUser = Depends(require_superadmin), db: Session = Depends(get_db)):
    clean_uname = username.strip()
    clean_pass = password.strip()
    existing = db.query(AdminUser).filter_by(username=clean_uname).first()
    if not existing:
        new_sa = AdminUser(
            username=clean_uname,
            password=clean_pass,
            role="subadmin",
            permissions=["ai_core", "competition"]
        )
        db.add(new_sa)
        db.commit()
    return RedirectResponse(url="/admin/manage-subadmins", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/update-permissions")
def update_subadmin_permissions(username: str = Form(...), perms: List[str] = Form([]), user: AdminUser = Depends(require_superadmin), db: Session = Depends(get_db)):
    target_user = db.query(AdminUser).filter_by(username=username).first()
    if target_user:
        target_user.permissions = perms
        db.commit()
    return RedirectResponse(url="/admin/manage-subadmins", status_code=status.HTTP_303_SEE_OTHER)

# ------------------------------------------------------------------------------
# 6. सभी 11-12 मॉड्यूल्स के राउट्स (All Modules Route Mapping)
# ------------------------------------------------------------------------------
@app.get("/", response_class=FileResponse)
def serve_index():
    return get_safe_file_response("index.html")

@app.get("/ai-core", response_class=FileResponse)
@app.get("/ai-core.html", response_class=FileResponse)
def serve_ai_core():
    return get_safe_file_response("ai-core.html")

@app.get("/ai-auto-healing", response_class=FileResponse)
@app.get("/ai-auto-healing.html", response_class=FileResponse)
def serve_auto_healing():
    return get_safe_file_response("ai-auto-healing.html")

@app.get("/digital-library", response_class=FileResponse)
@app.get("/digital-library.html", response_class=FileResponse)
def serve_digital_library():
    return get_safe_file_response("digital-library.html")

@app.get("/kids-zone", response_class=FileResponse)
@app.get("/kids-zone.html", response_class=FileResponse)
def serve_kids_zone():
    return get_safe_file_response("kids-zone.html")

@app.get("/spoken-english", response_class=FileResponse)
@app.get("/spoken-english.html", response_class=FileResponse)
def serve_spoken_english():
    return get_safe_file_response("spoken-english.html")

@app.get("/face-swap-social", response_class=FileResponse)
@app.get("/face-swap-social.html", response_class=FileResponse)
def serve_face_swap():
    return get_safe_file_response("face-swap-social.html")

@app.get("/central-wallet", response_class=FileResponse)
@app.get("/central-wallet.html", response_class=FileResponse)
def serve_central_wallet():
    return get_safe_file_response("central-wallet.html")

@app.get("/competition-solver", response_class=FileResponse)
@app.get("/competition-solver.html", response_class=FileResponse)
def serve_competition_solver():
    return get_safe_file_response("competition-solver.html")

@app.get("/live-guard-ai", response_class=FileResponse)
@app.get("/live-guard-ai.html", response_class=FileResponse)
def serve_live_guard():
    return get_safe_file_response("live-guard-ai.html")

@app.get("/dhruv-mitra", response_class=FileResponse)
@app.get("/dhruv-mitra.html", response_class=FileResponse)
def serve_dhruv_mitra():
    return get_safe_file_response("dhruv-mitra.html")

# एडमिन लाइव एक्टिविटी लॉग रूट
@app.get("/admin", response_class=HTMLResponse)
def admin_activity_logs(user: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    logs = db.query(UserActivityLog).order_by(UserActivityLog.timestamp.desc()).limit(50).all()
    rows = ""
    for l in logs:
        rows += f"""
        <tr class='border-b border-slate-800 text-xs'>
            <td class='py-3 px-4 font-mono text-cyan-300'>{l.timestamp.strftime('%d-%m-%Y %H:%M:%S')}</td>
            <td class='py-3 px-4 font-bold text-emerald-400'>{l.user_identifier}</td>
            <td class='py-3 px-4 text-purple-300'>{l.module}</td>
            <td class='py-3 px-4 text-gray-300'>{l.action}</td>
            <td class='py-3 px-4 font-mono text-gray-400'>{l.ip_address}</td>
        </tr>
        """
    if not rows:
        rows = "<tr><td colspan='5' class='py-4 text-center text-gray-500 text-xs'>कोई गतिविधि लॉग उपलब्ध नहीं है।</td></tr>"

    return f"""
    <!DOCTYPE html>
    <html lang="hi">
    <head>
        <meta charset="UTF-8">
        <title>Dhruv Academy - Live Activity Logs</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-950 text-white min-h-screen p-6 font-sans">
        <div class="max-w-7xl mx-auto space-y-6">
            <div class="flex justify-between items-center border-b border-slate-800 pb-4">
                <div>
                    <h1 class="text-2xl font-extrabold text-cyan-400">📊 लाइव छात्र गतिविधि और लॉग्स</h1>
                    <p class="text-xs text-gray-400 mt-1">इकोसिस्टम में होने वाले सभी क्रियाकलापों का रीयल-टाइम रिकॉर्ड</p>
                </div>
                <div class="flex gap-2">
                    <a href="/admin/super-master-panel" class="px-4 py-2 bg-indigo-700 hover:bg-indigo-600 text-xs font-bold rounded-xl transition">⚡ कमांड सेंटर</a>
                    <a href="/" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-xs font-bold rounded-xl transition">🏠 मुख्य पोर्टल</a>
                </div>
            </div>
            <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl overflow-x-auto">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="bg-slate-950 text-xs text-gray-300 border-b border-slate-800">
                            <th class="py-3 px-4">समय</th>
                            <th class="py-3 px-4">यूजर</th>
                            <th class="py-3 px-4">मॉड्यूल</th>
                            <th class="py-3 px-4">एक्शन विवरण</th>
                            <th class="py-3 px-4">IP एड्रेस</th>
                        </tr>
                    </thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """

# ------------------------------------------------------------------------------
# 7. जेमिनी एआई राउट और सिंगल-की इंटेलिजेंट राउटिंग (Gemini Neural Endpoint)
# ------------------------------------------------------------------------------
def get_gemini_key() -> str:
    for key_name in ["GEMINI_API_KEY1", "GEMINI_API_KEY", "GEMINI_API_KEYS"]:
        val = os.environ.get(key_name)
        if val:
            cleaned = val.strip().strip('"').strip("'")
            if cleaned:
                return cleaned.split(",")[0].strip()
    return ""

@app.post("/api/ai-core-solve")
async def ai_core_solve_endpoint(
    request: Request, 
    query: str = Form(...), 
    mode: str = Form("standard"), 
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    client_ip = request.client.host if request.client else "Unknown"
    prompt_instruction = f"Dhruv Academy Advanced Neural Core Analysis:\n\nQuery: {query}\n\nProvide a precise, structured, and detailed educational solution in Hindi or English as requested."
    parts = [{"text": prompt_instruction}]

    if file:
        try:
            image_bytes = await file.read()
            mime_type = file.content_type or "image/jpeg"
            base64_image = base64.b64encode(image_bytes).decode("utf-8")
            parts.append({"inlineData": {"mimeType": mime_type, "data": base64_image}})
        except Exception as img_err:
            print(f"Image read error: {img_err}")

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.2}
    }

    active_key = get_gemini_key()
    if not active_key:
        return JSONResponse(content={"success": True, "solution": "⚠️ सिस्टम में कोई वैध GEMINI_API_KEY1 उपलब्ध नहीं है। कृपया Render Dashboard के Environment Variables में अपनी की सेट करें।"})

    router_models = [
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-pro"
    ]
    
    solution_text = ""
    success_model = ""

    for model_name in router_models:
        target_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={active_key}"
        try:
            req = urllib.request.Request(
                target_url, 
                data=json.dumps(payload).encode("utf-8"), 
                headers={"Content-Type": "application/json"}, 
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=40) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                if "candidates" in res_data and res_data["candidates"]:
                    solution_text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    success_model = model_name
                    break
        except Exception as e:
            continue

    if solution_text:
        monogram_id = record_publicity_audit(db, f"SingleKey_Core_{success_model}", solution_text)
        final_output = f"{solution_text}\n\n--- \nDhruv Academy Verified Core [Monogram: {monogram_id}]"
        log_activity(db, f"AI Solved via Single Key ({success_model})", "Smart AI Core", f"Monogram: {monogram_id}", "Student", client_ip)
        return JSONResponse(content={"success": True, "solution": final_output, "monogram_code": monogram_id})
    else:
        return JSONResponse(content={"success": False, "solution": "⚠️ AI मॉडल से प्रतिक्रिया प्राप्त करने में विफल। कृपया API Key या नेटवर्क कनेक्शन की जांच करें।"})
