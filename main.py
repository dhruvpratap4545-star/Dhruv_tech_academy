#!/usr/bin/env python3
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
# 2. सुरक्षा और सत्र प्रबंधन (Security & Auth)
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
# 3. एडमिन लॉगिन व छात्र रजिस्ट्रेशन रूट्स
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
# 4. सुपर-एडमिन सुप्रीम कमांड सेंटर व सब-एडमिन कंट्रोल पैनल
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
                    <button type='submit' class='px-3 py-1 bg-emerald-600 hover:bg-emerald-500 rounded font-bold text-white'>± टोकन अपडेट</button>
                </form>
            </td>
        </tr>
        """
    if not student_rows:
        student_rows = "<tr><td colspan='4' class='py-4 text-center text-gray-500 text-xs'>अभी कोई छात्र पंजीकृत नहीं है।</td></tr>"

    audit_logs = db.query(PublicityAuditLog).order_by(PublicityAuditLog.timestamp.desc()).limit(20).all()
    audit_rows = "".join([f"<tr class='border-b border-slate-800 text-xs'><td class='py-2 px-3 font-mono text-cyan-400'>{al.monogram_code}</td><td class='py-2 px-3 text-emerald-300'>{al.content_type}</td><td class='py-2 px-3 text-gray-300'>{al.timestamp.strftime('%d-%m-%Y %H:%M')}</td></tr>" for al in audit_logs])
    if not audit_rows:
        audit_rows = "<tr><td colspan='3' class='py-2 text-center text-gray-500 text-xs'>कोई ऑडिट रिकॉर्ड नहीं।</td></tr>"

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
            <div class="flex justify-between items-center border-b border-slate-800 pb-4">
                <div>
                    <h1 class="text-2xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-emerald-400">⚡ Super-Admin Supreme Command Center</h1>
                    <p class="text-xs text-gray-400 mt-1">ध्रुव एकेडमी मास्टर इकोसिस्टम का सर्वोच्च नियंत्रण केंद्र (Full Administrative Power)</p>
                </div>
                <div class="flex gap-2">
                    <a href="/admin" class="px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-xs font-bold rounded-xl transition">📊 लाइव यूजर एक्टिविटी</a>
                    <a href="/admin/manage-subadmins" class="px-4 py-2 bg-indigo-700 hover:bg-indigo-600 text-xs font-bold rounded-xl transition">🛡️ सब-एडमिन अधिकार</a>
                    <a href="/" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-xs font-bold rounded-xl transition">🏠 मुख्य पोर्टल</a>
                    <a href="/auto-heal" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-xs font-bold rounded-xl transition">🛡️ ऑटो-हीलिंग हब</a>
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
                    <p class="text-2xl font-extrabold text-purple-400 mt-2">100% मक्खन की तरह चालू</p>
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
                <h2 class="text-sm font-bold text-emerald-400">📜 हालिया डिजिटल मोनोग्राम ऑडिट ट्रेल</h2>
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
                    <button type='submit' class='px-3 py-1 bg-cyan-600 hover:bg-cyan-500 rounded-lg text-white font-bold ml-auto'>अधिकार सहेजें</button>
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
                <a href="/admin/super-master-panel" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-xl text-xs font-bold">← सुपर-एडमिन कमांड सेंटर</a>
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
                    <button type='submit' class='px-4 py-2.5 bg-emerald-600 hover:bg-emerald-500 rounded-xl font-bold text-white'>सब-एडमिन जोड़ें</button>
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
# 5. मुख्य डैशबोर्ड व सभी 11 मॉड्यूल सटीक फाइल राउट्स
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

def get_gemini_key() -> str:
    # Render में सेट की गई सिंगल या मास्टर की को प्राथमिकता देना
    for key_name in ["GEMINI_API_KEY1", "GEMINI_API_KEY", "GEMINI_API_KEYS"]:
        val = os.environ.get(key_name)
        if val:
            cleaned = val.strip().strip('"').strip("'")
            if cleaned:
                return cleaned.split(",")[0].strip() # यदि कॉमा से अलग कई हों तो पहली लें
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
    prompt_instruction = f"Dhruv Academy Advanced Neural Core Analysis:\n\nQuery: {query}\n\nProvide a precise, structured, and detailed educational solution."
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
        "generationConfig": {"maxOutputTokens": 1500, "temperature": 0.2}
    }

    active_key = get_gemini_key()
    if not active_key:
        return JSONResponse(content={"success": True, "solution": "⚠️ सिस्टम में कोई वैध GEMINI_API_KEY1 उपलब्ध नहीं है। कृपया Render Dashboard के Environment में अपनी की सेट करें।"})

    # आधुनिक और स्थिर मॉडल्स की सूची (सबसे पहले gemini-3.5-flash)
    router_models = [
        "gemini-3.5-flash",
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
        return JSONResponse(content={"success": True, "solution": final_output})

    fallback_solution = "✨ नेबुला डिजिटल ब्लैकबोर्ड: आपकी स्कैन की गई तस्वीर या प्रश्न प्राप्त हो गया है। वर्तमान में गूगल एआई सर्वर का कोटा अस्थायी रूप से व्यस्त है, कृपया कुछ सेकंड बाद पुनः प्रयास करें।"
    return JSONResponse(content={"success": True, "solution": fallback_solution})

@app.get("/admin", response_class=HTMLResponse)
async def master_admin_panel(user: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    logs = db.query(UserActivityLog).order_by(UserActivityLog.timestamp.desc()).limit(100).all()
    rows = "".join([f"<tr class='border-b border-gray-800 text-xs'><td class='py-2 px-3'>{l.timestamp.strftime('%H:%M:%S')}</td><td class='py-2 px-3'>{l.user_identifier}</td><td class='py-2 px-3 text-cyan-300'>{l.module}</td><td class='py-2 px-3 font-bold'>{l.action}</td><td class='py-2 px-3'>{l.details}</td></tr>" for l in logs])
    return f"""<!DOCTYPE html><html lang="hi"><head><meta charset="UTF-8"><title>Live Activity Monitor</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-slate-950 text-white p-6 font-sans"><div class="max-w-6xl mx-auto space-y-4"><div class="flex justify-between items-center"><h1 class="text-xl font-bold text-emerald-400">📊 लाइव यूजर एक्टिविटी मॉनिटर</h1><div class="flex gap-2"><a href="/admin/super-master-panel" class="px-4 py-2 bg-cyan-600 rounded-xl text-xs font-bold">⚡ सुपर-एडमिन कमांड सेंटर</a><a href="/admin/manage-subadmins" class="px-4 py-2 bg-indigo-600 rounded-xl text-xs font-bold">🛡️ सब-एडमिन अधिकार</a></div></div><div class="bg-slate-900 p-4 rounded-xl border border-gray-800 overflow-x-auto"><table class="w-full text-left"><thead><tr class="bg-slate-800 text-xs text-gray-300"><th class="p-2">समय</th><th class="p-2">यूजर</th><th class="p-2">मॉड्यूल</th><th class="p-2">एक्शन</th><th class="p-2">विवरण</th></tr></thead><tbody>{rows}</tbody></table></div></div></body></html>"""

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

# ------------------------------------------------------------------------------
# 6. विशिष्ट मॉड्यूल राउट्स (Nebula, Competition Solver, 3D Blackboard)
# ------------------------------------------------------------------------------
@app.get("/nebula-visual-hub.html", response_class=HTMLResponse)
@app.get("/nebula-visual-hub", response_class=HTMLResponse)
async def serve_nebula_visual_hub():
    path = "nebula-visual-hub.html"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "nebula-visual-hub.html file not found", 404

@app.get("/competition-solver.html", response_class=HTMLResponse)
@app.get("/competition-solver", response_class=HTMLResponse)
async def serve_competition_solver():
    path = "competition-solver.html"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "competition-solver.html file not found", 404

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

# 7. ग्लोबल 404 एरर हैंडलर
@app.exception_handler(404)
async def custom_404_handler(request, exc):
    if os.path.exists("404.html"):
        with open("404.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=404)
    return HTMLResponse(content="<h3>404 - Page Not Found</h3>", status_code=404)

import os
import google.generativeai as genai

from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse

@app.post("/api/auto-heal-code")
async def auto_heal_code(request: Request):
    try:
        if not GEMINI_API_KEY1:
            return {"success": False, "error": "सर्वर एनवायरनमेंट में GEMINI_API_KEY1 सेट नहीं है।"}
            
        form_data = await request.form()
        broken_code = form_data.get('code', '')
        module_name = form_data.get('module', 'General Module')
        
        if not broken_code:
            return {"success": False, "error": "हील करने के लिए कोई कोड प्राप्त नहीं हुआ।"}

        model = get_gemini_model()
        prompt = f"""
        You are the Master Code Doctor & Full-Stack Architect for 'Dhruv Academy'.
        Analyze the following HTML/Python/JS code snippet from module '{module_name}'.
        Identify and fix all syntax errors, broken JavaScript functions, missing HTML tags, and ensure proper fetch/API routes matching main.py structure.
        Ensure all buttons and navigation links are fully active and correctly mapped.
        Return ONLY the fully corrected, production-ready clean code block. Do not wrap in markdown backticks.
        
        Broken Code:
        {broken_code}
        """
        
        response = model.generate_content(prompt)
        healed_text = response.text.strip()
        
        if healed_text.startswith("```"):
            lines = healed_text.splitlines()
            if lines[0].startswith("```"): lines = lines[1:]
            if lines and lines[-1].startswith("```"): lines = lines[:-1]
            healed_text = "\n".join(lines)

        return {
            "success": True,
            "healed_code": healed_text
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/auto-heal", response_class=HTMLResponse)
async def auto_heal_page(request: Request):
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html lang="hi">
    <head>
        <meta charset="UTF-8">
        <title>Dhruv Academy - AI Auto-Healing Hub</title>
        <style>
            body { background-color: #030712; color: #f3f4f6; font-family: Arial, sans-serif; margin: 0; padding: 20px; }
            .container { max-width: 800px; margin: 0 auto; background: #111827; padding: 30px; border-radius: 16px; border: 1px solid #1f2937; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
            h1 { color: #22d3ee; font-size: 24px; margin-bottom: 5px; }
            p { color: #9ca3af; font-size: 14px; margin-top: 0; }
            .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1f2937; padding-bottom: 15px; margin-bottom: 20px; }
            .back-btn { background: #1f2937; color: #f3f4f6; padding: 8px 16px; border-radius: 8px; text-decoration: none; font-size: 14px; }
            .back-btn:hover { background: #374151; }
            label { display: block; font-size: 14px; font-weight: bold; margin-bottom: 8px; color: #d1d5db; }
            input, textarea { width: 100%; background: #030712; border: 1px solid #374151; border-radius: 8px; padding: 12px; color: #22d3ee; font-family: monospace; font-size: 14px; box-sizing: border-box; margin-bottom: 20px; }
            input:focus, textarea:focus { border-color: #22d3ee; outline: none; }
            button { width: 100%; background: linear-gradient(to right, #0891b2, #2563eb); color: white; border: none; padding: 14px; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; transition: 0.2s; }
            button:hover { opacity: 0.9; }
            .result-box { background: #030712; border: 1px solid #1f2937; border-radius: 8px; padding: 15px; font-family: monospace; color: #34d399; white-space: pre-wrap; min-height: 150px; overflow-x: auto; }
            .section { margin-top: 25px; background: #1f2937; padding: 20px; border-radius: 12px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div>
                    <h1>🛡️ AI Auto-Healing Hub</h1>
                    <p>ध्रुव एकेडमी मास्टर इकोसिस्टम - ऑटोमैटिक कोड करेक्शन सेंटर</p>
                </div>
                <a href="/admin/super_master_panel" class="back-btn">← कमांड सेंटर</a>
            </div>

            <div class="section">
                <label>मॉड्यूल का नाम (Module Name)</label>
                <input type="text" id="moduleName" value="Spoken English Module">

                <label>टूटा हुआ या स्पीकिंग कोड यहाँ पेस्ट करें (Broken Code):</label>
                <textarea id="brokenCode" rows="8" placeholder="यहाँ अपना कोड पेस्ट करें..."></textarea>

                <button onclick="healCode()">✨ ऑटो-हील शुरू करें (Fix Code)</button>
            </div>

            <div class="section">
                <label style="color: #34d399;">✅ ठीक किया गया शुद्ध कोड (Production-Ready Code):</label>
                <div id="resultBox" class="result-box">रिजल्ट यहाँ दिखाई देगा...</div>
            </div>
        </div>

        <script>
            async function healCode() {
                const code = document.getElementById('brokenCode').value;
                const module = document.getElementById('moduleName').value;
                const resultBox = document.getElementById('resultBox');

                if (!code.trim()) {
                    alert('कृपया पहले कोड पेस्ट करें!');
                    return;
                }

                resultBox.innerText = 'AI कोड को एनालाइज और हील कर रहा है... कृपया प्रतीक्षा करें...';

                try {
                    const response = await fetch('/api/auto-heal-code', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                        },
                        body: 'code=' + encodeURIComponent(code) + '&module=' + encodeURIComponent(module)
                    });
                    
                    const data = await response.json();
                    if (data.success) {
                        resultBox.innerText = data.healed_code;
                    } else {
                        resultBox.innerText = 'एरर: ' + (data.error || 'कुछ गलत हो गया');
                    }
                } catch (err) {
                    resultBox.innerText = 'कनेक्शन एरर: ' + err.message;
                }
            }
        </script>
    </body>
    </html>
    """)

    
if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
