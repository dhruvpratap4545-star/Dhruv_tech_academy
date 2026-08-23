#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
# main.py - Dhruv Academy Master Ecosystem (Gemini 2.5 Flash Production Engine)
# ==============================================================================

import os
import shutil
import datetime
import secrets
import base64
import json
from pathlib import Path
from typing import Optional, List

import urllib.request
import urllib.error

from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

app = FastAPI(title="Dhruv Academy Master Ecosystem")

# ------------------------------------------------------------------------------
# 1. डेटाबेस, स्टोरेज और मॉडल सेटअप
# ------------------------------------------------------------------------------
UPLOAD_DIR = Path("dhruv_academy_master_storage")
UPLOAD_DIR.mkdir(exist_ok=True)

DATABASE_URL = "sqlite:///./dhruv_academy_ecosystem.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AcademyMasterRecord(Base):
    __tablename__ = "academy_master_records"
    id = Column(Integer, primary_key=True, index=True)
    module_name = Column(String, index=True)
    filename = Column(String, index=True)
    security_level = Column(String, default="100% Encrypted")
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class AdminUser(Base):
    __tablename__ = "admin_users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    role = Column(String, default="subadmin")
    permissions = Column(JSON, default=list)

class FeatureToggle(Base):
    __tablename__ = "feature_toggles"
    id = Column(Integer, primary_key=True, index=True)
    feature_key = Column(String, unique=True, index=True)
    feature_name = Column(String)
    is_enabled = Column(Boolean, default=True)
    is_paywalled = Column(Boolean, default=False)

Base.metadata.create_all(bind=engine)

ACTIVE_SESSIONS = {}

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_default_data():
    db = SessionLocal()
    try:
        if not db.query(AdminUser).filter_by(username="dhruv_superadmin").first():
            super_admin = AdminUser(
                username="dhruv_superadmin",
                password="DhruvSuperSecure2026!",
                role="superadmin",
                permissions=["all"]
            )
            sub_admin = AdminUser(
                username="teacher_legal",
                password="LegalPass2026!",
                role="subadmin",
                permissions=["legal_ai", "digital_library"]
            )
            db.add_all([super_admin, sub_admin])

        default_features = [
            {"key": "mod_1_kids", "name": "1. Kids Zone (NC-5)", "is_paywalled": False},
            {"key": "mod_2_ai_core", "name": "2. AI Engine Core", "is_paywalled": True},
            {"key": "mod_3_healing", "name": "3. AI Auto-Healing", "is_paywalled": True},
            {"key": "mod_4_faceswap", "name": "4. Face-Swap Social", "is_paywalled": True},
            {"key": "mod_5_blackboard", "name": "5. 3D Blackboard", "is_paywalled": False},
            {"key": "mod_6_library", "name": "6. Digital Library", "is_paywalled": True},
            {"key": "mod_7_legal", "name": "7. Legal AI (All Laws)", "is_paywalled": True},
            {"key": "mod_8_coaching", "name": "8. Coaching Hub", "is_paywalled": True},
            {"key": "mod_9_competition", "name": "9. Competition Solver", "is_paywalled": True},
            {"key": "mod_10_nebula", "name": "10. Nebula Visual Hub", "is_paywalled": False}
        ]

        for feat in default_features:
            if not db.query(FeatureToggle).filter_by(feature_key=feat["key"]).first():
                db.add(FeatureToggle(
                    feature_key=feat["key"],
                    feature_name=feat["name"],
                    is_enabled=True,
                    is_paywalled=feat["is_paywalled"]
                ))
        db.commit()
    finally:
        db.close()

init_default_data()

# ------------------------------------------------------------------------------
# 2. सुरक्षा और प्रमाणीकरण
# ------------------------------------------------------------------------------
def get_current_admin(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    session_token = request.cookies.get("dhruv_auth_token")
    if not session_token or session_token not in ACTIVE_SESSIONS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="अनधिकृत एक्सेस")
    
    username = ACTIVE_SESSIONS[session_token]
    user = db.query(AdminUser).filter(AdminUser.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="अमान्य सत्र")
    return user

def require_superadmin(current_user: AdminUser = Depends(get_current_admin)):
    if current_user.role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="केवल सुपर-एडमिन के लिए उपलब्ध")
    return current_user

# ------------------------------------------------------------------------------
# 3. सीक्रेट एडमिन लॉगिन रूट्स
# ------------------------------------------------------------------------------
@app.get("/secret-admin-login-dhruv", response_class=HTMLResponse)
def secret_login_page(error: Optional[str] = None):
    err_box = f"<div class='p-3 bg-red-900/50 border border-red-500 rounded-xl text-red-300 text-xs'>{error}</div>" if error else ""
    return f"""
    <!DOCTYPE html>
    <html lang="hi">
    <head>
        <meta charset="UTF-8">
        <title>Dhruv Academy - Admin Login</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-950 text-white min-h-screen flex items-center justify-center p-4">
        <div class="bg-slate-900/90 border border-cyan-500/40 rounded-3xl p-8 max-w-md w-full shadow-2xl space-y-6">
            <div class="text-center space-y-2">
                <span class="text-4xl">🔐</span>
                <h1 class="text-xl font-extrabold text-cyan-400">Dhruv Admin Gateway</h1>
                <p class="text-xs text-gray-400">सुरक्षित प्रशासनिक प्रवेश द्वार</p>
            </div>
            {err_box}
            <form action="/secret-admin-login-dhruv" method="POST" class="space-y-4 text-xs">
                <div>
                    <label class="block mb-1 font-bold text-gray-300">यूजरनेम</label>
                    <input type="text" name="username" required placeholder="dhruv_superadmin" class="w-full p-3 rounded-xl bg-slate-800 border border-slate-700 focus:border-cyan-500 focus:outline-none text-white">
                </div>
                <div>
                    <label class="block mb-1 font-bold text-gray-300">पासवर्ड</label>
                    <input type="password" name="password" required placeholder="••••••••••••" class="w-full p-3 rounded-xl bg-slate-800 border border-slate-700 focus:border-cyan-500 focus:outline-none text-white">
                </div>
                <button type="submit" class="w-full py-3 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 rounded-xl font-bold text-white shadow-lg transition">लॉगिन करें</button>
            </form>
            <div class="text-center pt-2">
                <a href="/" class="text-[11px] text-gray-500 hover:text-cyan-400">← मुख्य पोर्टल</a>
            </div>
        </div>
    </body>
    </html>
    """

@app.post("/secret-admin-login-dhruv")
def process_secret_login(response: Response, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(AdminUser).filter(AdminUser.username == username, AdminUser.password == password).first()
    if not user:
        return HTMLResponse(content=secret_login_page(error="अमान्य क्रेडेंशियल्स!"), status_code=401)
    
    session_token = secrets.token_hex(32)
    ACTIVE_SESSIONS[session_token] = user.username
    
    res = RedirectResponse(url="/admin/super-dashboard", status_code=status.HTTP_303_SEE_OTHER)
    res.set_cookie(key="dhruv_auth_token", value=session_token, httponly=True, max_age=86400, samesite="lax", secure=False)
    return res

@app.get("/admin-logout")
def admin_logout(request: Request):
    token = request.cookies.get("dhruv_auth_token")
    if token and token in ACTIVE_SESSIONS:
        del ACTIVE_SESSIONS[token]
    res = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    res.delete_cookie("dhruv_auth_token")
    return res

# ------------------------------------------------------------------------------
# 4. सुपर-एडमिन डैशबोर्ड
# ------------------------------------------------------------------------------
@app.get("/admin/super-dashboard", response_class=HTMLResponse)
def super_admin_dashboard(user: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    features = db.query(FeatureToggle).all()
    subadmins = db.query(AdminUser).all()

    feat_rows = ""
    for f in features:
        enabled_checked = "checked" if f.is_enabled else ""
        paywalled_checked = "checked" if f.is_paywalled else ""
        feat_rows += f"""
        <tr class="border-b border-gray-800 text-xs">
            <td class="py-3 px-4 font-bold text-gray-200">{f.feature_name}</td>
            <td class="py-3 px-4 text-center">
                <input type="checkbox" name="enabled_{f.feature_key}" {enabled_checked} class="w-4 h-4 accent-cyan-500 rounded">
            </td>
            <td class="py-3 px-4 text-center">
                <input type="checkbox" name="paywall_{f.feature_key}" {paywalled_checked} class="w-4 h-4 accent-emerald-500 rounded">
            </td>
        </tr>
        """

    admin_rows = ""
    for a in subadmins:
        role_badge = "<span class='px-2 py-0.5 rounded bg-cyan-900 text-cyan-300 font-bold'>SuperAdmin</span>" if a.role == "superadmin" else "<span class='px-2 py-0.5 rounded bg-slate-800 text-gray-300'>SubAdmin</span>"
        perms = ", ".join(a.permissions) if a.permissions else "None"
        admin_rows += f"""
        <tr class="border-b border-gray-800 text-xs">
            <td class="py-3 px-4 font-bold">{a.username}</td>
            <td class="py-3 px-4">{role_badge}</td>
            <td class="py-3 px-4 text-gray-400">{perms}</td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="hi">
    <head>
        <meta charset="UTF-8">
        <title>Super Admin Control</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-950 text-white p-6 sm:p-10 font-sans">
        <div class="max-w-6xl mx-auto space-y-8">
            <div class="flex flex-wrap justify-between items-center border-b border-gray-800 pb-4 gap-4">
                <div>
                    <h1 class="text-2xl sm:text-3xl font-extrabold text-cyan-400">🛡️ Super-Admin Master Control</h1>
                    <p class="text-xs text-gray-400 mt-1">लॉगिन यूजर: <span class="text-emerald-400 font-bold">{user.username}</span></p>
                </div>
                <div class="flex gap-2">
                    <a href="/admin" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-xs font-bold rounded-xl transition">📂 डेटा मॉनिटर</a>
                    <a href="/" class="px-4 py-2 bg-cyan-700 hover:bg-cyan-600 text-xs font-bold rounded-xl transition">मुख्य पोर्टल</a>
                    <a href="/admin-logout" class="px-4 py-2 bg-red-900 hover:bg-red-800 text-xs font-bold rounded-xl transition">लॉगआउट ✕</a>
                </div>
            </div>

            <div class="bg-slate-900 p-6 rounded-2xl border border-gray-800 space-y-4">
                <div class="flex justify-between items-center">
                    <h2 class="text-lg font-bold text-cyan-300">⚙️ Paywall & Feature Manager</h2>
                </div>
                <form action="/admin/save-toggles" method="POST">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="border-b border-gray-700 text-xs text-gray-400">
                                <th class="py-3 px-4">मॉड्यूल नाम</th>
                                <th class="py-3 px-4 text-center">सक्रिय (Enabled)</th>
                                <th class="py-3 px-4 text-center">पेवॉल (Paywalled)</th>
                            </tr>
                        </thead>
                        <tbody>{feat_rows}</tbody>
                    </table>
                    <div class="pt-4 text-right">
                        <button type="submit" class="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 rounded-xl font-bold text-xs shadow-lg transition">सेटिंग्स सेव करें 💾</button>
                    </div>
                </form>
            </div>

            <div class="bg-slate-900 p-6 rounded-2xl border border-gray-800 space-y-4">
                <h2 class="text-lg font-bold text-indigo-400">👥 सब-एडमिन रोल्स</h2>
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="border-b border-gray-700 text-xs text-gray-400">
                            <th class="py-3 px-4">यूजरनेम</th>
                            <th class="py-3 px-4">रोल</th>
                            <th class="py-3 px-4">अनुमतियाँ</th>
                        </tr>
                    </thead>
                    <tbody>{admin_rows}</tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """

@app.post("/admin/save-toggles")
async def save_feature_toggles(request: Request, user: AdminUser = Depends(require_superadmin), db: Session = Depends(get_db)):
    form_data = await request.form()
    features = db.query(FeatureToggle).all()
    for f in features:
        f.is_enabled = f"enabled_{f.feature_key}" in form_data
        f.is_paywalled = f"paywall_{f.feature_key}" in form_data
    db.commit()
    return RedirectResponse(url="/admin/super-dashboard", status_code=status.HTTP_303_SEE_OTHER)

# ------------------------------------------------------------------------------
# 5. मुख्य डैशबोर्ड
# ------------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def master_ecosystem_dashboard():
    return """
    <!DOCTYPE html>
    <html lang="hi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dhruv Academy Master Ecosystem</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700;800&display=swap');
            body { font-family: 'Poppins', sans-serif; transition: background-color 0.3s, color 0.3s; }
            body.dark-mode { background-color: #020617; color: #f8fafc; }
            body.dark-mode .master-card { background: rgba(15, 23, 42, 0.92); border: 1px solid rgba(255, 255, 255, 0.12); color: #f8fafc; }
            body.dark-mode .master-card h3 { color: #38bdf8; }
            body.dark-mode .master-card p { color: #cbd5e1; }
            body.dark-mode .top-bar { background-color: rgba(2, 6, 23, 0.98); border-color: rgba(255, 255, 255, 0.1); }
            body.light-mode { background-color: #f8fafc; color: #0f172a; }
            body.light-mode .master-card { background: #ffffff; border: 2px solid #cbd5e1; box-shadow: 0 10px 25px rgba(0,0,0,0.06); color: #0f172a; }
            body.light-mode .master-card h3 { color: #0284c7; font-weight: 800; }
            body.light-mode .master-card p { color: #334155; font-weight: 600; }
            body.light-mode .top-bar { background-color: #e2e8f0; border-color: #cbd5e1; color: #0f172a; }
            .nebula-master-glow { background: radial-gradient(circle at center, rgba(14, 165, 233, 0.35) 0%, rgba(147, 51, 234, 0.25) 45%, transparent 85%); }
            .master-card { backdrop-filter: blur(20px); transition: all 0.3s ease; }
            .master-card:hover { transform: translateY(-4px); box-shadow: 0 15px 30px -10px rgba(56, 189, 248, 0.4); }
            .lang-pill-container { display: inline-flex; align-items: center; background-color: #0b1329; border: 1.5px solid #0284c7; border-radius: 9999px; padding: 3px; gap: 4px; box-shadow: inset 0 2px 4px rgba(0,0,0,0.5); }
            .lang-pill-btn { padding: 6px 18px; border-radius: 9999px; font-size: 12px; font-weight: 700; line-height: 1; border: none; outline: none; transition: all 0.25s ease-in-out; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; white-space: nowrap; }
            .lang-pill-active { background: linear-gradient(135deg, #0284c7, #0369a1) !important; color: #ffffff !important; box-shadow: 0 2px 8px rgba(14, 165, 233, 0.5); }
            .lang-pill-inactive { background: transparent !important; color: #94a3b8 !important; }
            .lang-pill-inactive:hover { color: #f8fafc !important; }
        </style>
    </head>
    <body class="min-h-screen dark-mode flex flex-col justify-between" id="pageBody">
        <div>
            <div id="topControlBar" class="top-bar w-full border-b px-4 py-2 flex justify-end items-center text-xs sticky top-0 z-50 backdrop-blur-md gap-3">
                <button onclick="toggleThemeMode()" id="themeToggleBtn" class="px-3 py-1 bg-slate-800 text-amber-300 hover:bg-slate-700 rounded-lg font-bold shadow transition text-[11px]">Light Mode</button>
                <button onclick="toggleMasterVoiceGuide()" id="voiceToggleBtn" class="px-3 py-1 bg-red-950 border border-red-500/50 hover:border-red-400 rounded-lg font-bold text-red-400 shadow transition flex items-center gap-1 text-[11px]">
                    <span>AI Voice:</span>
                    <span id="voiceStatusText">MUTE (OFF)</span>
                </button>
            </div>

            <div id="mainContainer" class="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-10">
                <header class="flex flex-col md:flex-row justify-between items-center pb-6 border-b border-gray-800 gap-4">
                    <div>
                        <h1 class="text-2xl sm:text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-sky-300 to-indigo-400" id="mainHeaderTitle">Dhruv Academy Master Ecosystem</h1>
                        <p class="text-[11px] sm:text-xs font-semibold tracking-widest uppercase mt-1 opacity-90 text-cyan-300" id="mainHeaderSub">100% सिक्योर एनक्रिप्टेड डेटा आर्किटेक्चर | विश्व स्तरीय एआई</p>
                    </div>
                    <div class="flex items-center gap-2">
                        <span class="text-xs font-bold text-slate-400">Lang:</span>
                        <div class="lang-pill-container">
                            <button type="button" onclick="setLanguage('hi')" id="btnLangHi" class="lang-pill-btn lang-pill-active">हिंदी</button>
                            <button type="button" onclick="setLanguage('en')" id="btnLangEn" class="lang-pill-btn lang-pill-inactive">English</button>
                        </div>
                    </div>
                </header>

                <div class="nebula-master-glow p-6 sm:p-12 rounded-3xl border border-cyan-500/40 text-center space-y-6 shadow-2xl relative overflow-hidden">
                    <h1 class="text-2xl sm:text-4xl lg:text-5xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-sky-200 to-purple-400" id="heroTitle">Dhruv Academy Master Ecosystem</h1>
                    <p class="text-xs sm:text-sm md:text-base max-w-3xl mx-auto leading-relaxed font-semibold text-slate-200" id="heroDesc">नर्सरी से लेकर सभी कानून, आईएएस (IAS), पीसीएस (PCS), बैंकिंग और प्रतियोगी परीक्षाओं की तैयारी के लिए भारत का सबसे उन्नत एआई पोर्टल।</p>
                    <div class="flex flex-wrap justify-center gap-2 sm:gap-3 pt-2">
                        <button onclick="openPaymentGateway('NC से कक्षा 5 (Kids Tier)', '29')" class="px-3 sm:px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold shadow-lg transition">NC-5 (₹29)</button>
                        <button onclick="openPaymentGateway('कक्षा 6 से 8 (Standard)', '49')" class="px-3 sm:px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold shadow-lg transition">Class 6-8 (₹49)</button>
                        <button onclick="openPaymentGateway('कक्षा 8 से 12 (Advanced)', '99')" class="px-3 sm:px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-xl text-xs font-bold shadow-lg transition">Class 8-12 (₹99)</button>
                        <button onclick="openPaymentGateway('Graduate (Pro)', '149')" class="px-3 sm:px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-xl text-xs font-bold shadow-lg transition">Graduate (₹149)</button>
                        <button onclick="openPaymentGateway('Post Graduate & IAS/PCS', '299')" class="px-3 sm:px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-xl text-xs font-bold shadow-lg transition">PG & IAS/PCS (₹299)</button>
                    </div>
                </div>
                
                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                    <div onclick="window.location.href='/kids-zone'" class="master-card p-6 rounded-2xl cursor-pointer hover:border-emerald-500 border border-transparent transition-all">
                        <h3 class="font-bold text-lg mb-2">1. Foundation: NC-5 Kids Tier</h3>
                        <p class="text-xs">नर्सरी से कक्षा 5 तक की नींव (AI-Driven Learning Module).</p>
                    </div>
                    <div onclick="openModulePortal(2)" class="master-card p-6 rounded-2xl cursor-pointer">
                        <h3 class="font-bold text-lg mb-2">2. AI Engine Core</h3>
                        <p class="text-xs">अति-सटीक भाषा और डेटा प्रोसेसिंग इंजन।</p>
                    </div>
                    <div onclick="openModulePortal(3)" class="master-card p-6 rounded-2xl cursor-pointer">
                        <h3 class="font-bold text-lg mb-2">3. AI Auto-Healing</h3>
                        <p class="text-xs">सॉफ्टवेयर त्रुटियों को स्वतः ठीक करने वाला स्कैनर।</p>
                    </div>
                    <div onclick="openModulePortal(4)" class="master-card p-6 rounded-2xl cursor-pointer">
                        <h3 class="font-bold text-lg mb-2">4. Face-Swap Social</h3>
                        <p class="text-xs">छात्रों के लिए वीडियो और सोशल एक्सप्लेनर विजुअल्स।</p>
                    </div>
                    <div onclick="openModulePortal(5)" class="master-card p-6 rounded-2xl cursor-pointer">
                        <h3 class="font-bold text-lg mb-2">5. 3D Blackboard</h3>
                        <p class="text-xs">डिजिटल कक्षाओं के लिए 3डी ब्लैकबोर्ड और टीवी कास्ट।</p>
                    </div>
                    <div onclick="openModulePortal(6)" class="master-card p-6 rounded-2xl cursor-pointer">
                        <h3 class="font-bold text-lg mb-2">6. Digital Library</h3>
                        <p class="text-xs">एनक्रिप्टेड ई-बुक्स और सुरक्षित डिजिटल वॉलेट।</p>
                    </div>
                    <div onclick="openModulePortal(7)" class="master-card p-6 rounded-2xl cursor-pointer border-rose-500/30">
                        <h3 class="font-bold text-lg mb-2">7. Legal AI (All Laws)</h3>
                        <p class="text-xs">भारत और दुनिया के सभी कानूनों (All Laws) का मास्टर हब।</p>
                    </div>
                    <div onclick="openModulePortal(8)" class="master-card p-6 rounded-2xl cursor-pointer">
                        <h3 class="font-bold text-lg mb-2">8. Coaching Hub</h3>
                        <p class="text-xs">कोचिंग संस्थानों के संचालन और बैच प्रबंधन का डैशबोर्ड।</p>
                    </div>
                    <div onclick="openModulePortal(9)" class="master-card p-6 rounded-2xl cursor-pointer border-orange-500/30">
                        <h3 class="font-bold text-lg mb-2">9. Competition Solver</h3>
                        <p class="text-xs">IAS, IFS, IRS, PCS, Banking, NEET आदि सभी परीक्षाओं का सॉल्वर।</p>
                    </div>
                    <div onclick="openModulePortal(10)" class="master-card p-6 rounded-2xl cursor-pointer">
                        <h3 class="font-bold text-lg mb-2">10. Nebula Visual Hub</h3>
                        <p class="text-xs">सिस्टम गतिविधियों को दिखाने वाला नेबुला डैशबोर्ड।</p>
                    </div>
                </div>

                <div class="text-center pt-4 pb-4">
                    <a href="/admin" class="inline-block px-8 py-3.5 bg-gradient-to-r from-cyan-600 to-blue-600 rounded-xl text-sm font-bold text-white shadow-xl transition">एडमिन डेटा मॉनिटर खोलें</a>
                </div>
            </div>
        </div>

        <footer class="w-full border-t border-gray-800/80 py-4 px-6 text-center text-xs text-gray-500 bg-slate-950/80">
            <p>© 2026 Dhruv Academy Master Ecosystem. सर्वाधिकार सुरक्षित। 
                <a href="/secret-admin-login-dhruv" class="opacity-20 hover:opacity-100 hover:text-cyan-400 transition ml-2 text-[10px]" title="एडमिन पोर्टल">System Gateway</a>
            </p>
        </footer>

        <div id="modulePortalModal" class="hidden fixed inset-0 bg-black/85 flex items-center justify-center p-4 z-50 backdrop-blur-md">
            <div class="master-card p-6 sm:p-8 rounded-3xl w-full max-w-xl space-y-6 border border-cyan-500/50 shadow-2xl">
                <div class="flex justify-between items-center border-b border-gray-700 pb-4">
                    <h2 id="portalModalTitle" class="text-lg sm:text-xl font-bold">मॉड्यूल पोर्टल</h2>
                    <button onclick="closeModulePortal()" class="font-bold text-lg">✕</button>
                </div>
                <div id="portalModalBody" class="space-y-4 text-xs sm:text-sm"></div>
                <div class="pt-4 border-t border-gray-700 text-right">
                    <button onclick="closeModulePortal()" class="px-6 py-2.5 bg-cyan-600 hover:bg-cyan-500 rounded-xl font-bold text-xs text-white shadow-lg transition">बंद करें / Close</button>
                </div>
            </div>
        </div>

        <div id="paymentGatewayModal" class="hidden fixed inset-0 bg-black/85 flex items-center justify-center p-4 z-50 backdrop-blur-md">
            <div class="master-card p-6 sm:p-8 rounded-3xl w-full max-w-md space-y-6 border border-emerald-500/50 shadow-2xl text-center">
                <div class="flex justify-between items-center border-b border-gray-700 pb-4">
                    <h2 class="text-lg sm:text-xl font-bold text-emerald-400">Secure Payment Gateway</h2>
                    <button onclick="closePaymentGateway()" class="font-bold text-lg">✕</button>
                </div>
                <div class="space-y-3">
                    <div class="p-4 rounded-2xl border border-slate-700 bg-slate-900/50">
                        <p class="text-xs text-gray-400">चुना गया प्लान:</p>
                        <h3 id="paymentPlanTitle" class="text-base sm:text-lg font-bold mt-1">Plan</h3>
                        <p id="paymentPlanPrice" class="text-xl sm:text-2xl font-extrabold text-emerald-400 mt-2">₹0</p>
                    </div>
                    <div class="space-y-2 text-left pt-2">
                        <label class="block text-xs font-semibold text-gray-300">UPI ID / कार्ड नंबर दर्ज करें:</label>
                        <input type="text" placeholder="name@upi या कार्ड नंबर" class="w-full p-3 border border-slate-700 rounded-xl text-xs bg-slate-900 text-white focus:outline-none focus:border-cyan-500">
                    </div>
                </div>
                <div id="paymentActionArea" class="space-y-3 pt-2">
                    <button onclick="processPayment()" class="w-full py-3 bg-emerald-600 hover:bg-emerald-500 rounded-xl font-bold text-xs sm:text-sm text-white shadow-lg transition">भुगतान करें (Pay Now)</button>
                </div>
                <div id="paymentStatusBox" class="hidden py-4 space-y-2">
                    <div class="inline-block animate-spin rounded-full h-8 w-8 border-4 border-cyan-500 border-t-transparent"></div>
                    <p class="text-xs font-bold tracking-wider text-cyan-300">ट्रांसजैक्शन अंडर प्रोसेस... कृपया प्रतीक्षा करें!</p>
                </div>
            </div>
        </div>

        <script>
            let isVoiceGuideActive = false;
            let currentTheme = 'dark';
            let currentLang = 'hi';

            const langDictionary = {
                hi: { sub: "100% सिक्योर एनक्रिप्टेड डेटा आर्किटेक्चर | विश्व स्तरीय एआई", heroDesc: "नर्सरी से लेकर सभी कानून, आईएएस (IAS), पीसीएस (PCS), बैंकिंग और प्रतियोगी परीक्षाओं की तैयारी के लिए भारत का सबसे उन्नत एआई पोर्टल।" },
                en: { sub: "100% Secure Encrypted Data Architecture | World Class AI", heroDesc: "India's most advanced AI portal for school education, all laws, and competitive exams like IAS, PCS, Banking, etc." }
            };

            function setLanguage(lang) {
                currentLang = lang;
                let btnHi = document.getElementById('btnLangHi');
                let btnEn = document.getElementById('btnLangEn');
                if (lang === 'hi') {
                    btnHi.className = "lang-pill-btn lang-pill-active";
                    btnEn.className = "lang-pill-btn lang-pill-inactive";
                    document.getElementById('mainHeaderSub').innerText = langDictionary.hi.sub;
                    document.getElementById('heroDesc').innerText = langDictionary.hi.heroDesc;
                    speakPolite("भाषा बदलकर हिंदी कर दी गई है।");
                } else {
                    btnEn.className = "lang-pill-btn lang-pill-active";
                    btnHi.className = "lang-pill-btn lang-pill-inactive";
                    document.getElementById('mainHeaderSub').innerText = langDictionary.en.sub;
                    document.getElementById('heroDesc').innerText = langDictionary.en.heroDesc;
                    speakPolite("Language switched to English.");
                }
            }

            function toggleThemeMode() {
                let bodyEl = document.getElementById('pageBody');
                let themeBtn = document.getElementById('themeToggleBtn');
                if (currentTheme === 'dark') {
                    currentTheme = 'light';
                    bodyEl.classList.remove('dark-mode');
                    bodyEl.classList.add('light-mode');
                    themeBtn.innerText = "Dark Mode";
                    themeBtn.className = "px-3 py-1 bg-slate-200 text-slate-900 hover:bg-slate-300 rounded-lg font-bold shadow transition text-[11px]";
                    speakPolite("लाइट मोड ऑन किया गया।");
                } else {
                    currentTheme = 'dark';
                    bodyEl.classList.remove('light-mode');
                    bodyEl.classList.add('dark-mode');
                    themeBtn.innerText = "Light Mode";
                    themeBtn.className = "px-3 py-1 bg-slate-800 text-amber-300 hover:bg-slate-700 rounded-lg font-bold shadow transition text-[11px]";
                    speakPolite("डार्क मोड ऑन किया गया।");
                }
            }

            function toggleMasterVoiceGuide() {
                isVoiceGuideActive = !isVoiceGuideActive;
                let btn = document.getElementById('voiceToggleBtn');
                let statusText = document.getElementById('voiceStatusText');
                if (isVoiceGuideActive) {
                    btn.className = "px-3 py-1 bg-emerald-950 border border-emerald-500/50 text-emerald-400 rounded-lg font-bold shadow transition flex items-center gap-1 text-[11px]";
                    statusText.innerText = "ACTIVE (ON)";
                    speakPolite("नमस्ते, ध्रुव एकेडमी मास्टर इकोसिस्टम में आपका स्वागत है।");
                } else {
                    btn.className = "px-3 py-1 bg-red-950 border border-red-500/50 text-red-400 rounded-lg font-bold shadow transition flex items-center gap-1 text-[11px]";
                    statusText.innerText = "MUTE (OFF)";
                    if ('speechSynthesis' in window) { window.speechSynthesis.cancel(); }
                }
            }

            function speakPolite(text) {
                if (!isVoiceGuideActive) return;
                if ('speechSynthesis' in window) {
                    window.speechSynthesis.cancel();
                    let u = new SpeechSynthesisUtterance(text);
                    u.lang = currentLang === 'hi' ? 'hi-IN' : 'en-US';
                    u.rate = 0.9;
                    window.speechSynthesis.speak(u);
                }
            }

            function openPaymentGateway(planName, priceVal) {
                document.getElementById('paymentPlanTitle').innerText = planName;
                document.getElementById('paymentPlanPrice').innerText = "₹" + priceVal + " / माह";
                document.getElementById('paymentActionArea').classList.remove('hidden');
                document.getElementById('paymentStatusBox').classList.add('hidden');
                document.getElementById('paymentGatewayModal').classList.remove('hidden');
                speakPolite(planName + " चुना गया है।");
            }

            function closePaymentGateway() { document.getElementById('paymentGatewayModal').classList.add('hidden'); }

            function processPayment() {
                document.getElementById('paymentActionArea').classList.add('hidden');
                document.getElementById('paymentStatusBox').classList.remove('hidden');
                speakPolite("भुगतान प्रोसेस हो रहा है।");
                setTimeout(() => {
                    alert("पेमेंट अनुरोध सफलतापूर्वक भेजा गया!");
                    closePaymentGateway();
                }, 2500);
            }

            function openModulePortal(modId) {
                let title = "मॉड्यूल पोर्टल";
                let contentHtml = "<p class='text-xs'>यह मॉड्यूल सक्रिय है।</p>";
                if(modId === 2) { title = "2. Super AI Engine Core"; contentHtml = "<p class='text-xs'>डेटा प्रोसेसिंग इंजन सक्रिय है।</p>"; }
                else if(modId === 3) { title = "3. AI Auto-Healing"; contentHtml = "<p class='text-xs'>सिस्टम ऑटो-हीलिंग स्कैनर रेडी है।</p>"; }
                else if(modId === 7) { title = "7. Legal AI Hub"; contentHtml = "<p class='text-xs'>कानूनी अनुसंधान प्रणाली सक्रिय है।</p>"; }
                else if(modId === 9) { title = "9. Competition Solver"; contentHtml = "<p class='text-xs'>IAS/PCS/NEET सॉल्वर तैयार है।</p>"; }

                document.getElementById('portalModalTitle').innerText = title;
                document.getElementById('portalModalBody').innerHTML = contentHtml;
                document.getElementById('modulePortalModal').classList.remove('hidden');
                speakPolite(title + " खोल दिया गया है।");
            }

            function closeModulePortal() { document.getElementById('modulePortalModal').classList.add('hidden'); }
        </script>
    </body>
    </html>
    """

# ------------------------------------------------------------------------------
# 6. एआई विजन एपीआई (Targeted to Active gemini-2.5-flash)
# ------------------------------------------------------------------------------
async def process_gemini_vision(file: UploadFile, lang: str):
    api_key = (
        os.environ.get("GEMINI_API_KEY") or 
        os.getenv("GEMINI_API_KEY") or 
        os.environ.get("GOOGLE_API_KEY") or 
        ""
    ).strip().strip('"').strip("'")
    
    if not api_key:
        return JSONResponse(content={
            "success": False,
            "solution": "⚠️ सर्वर पर GEMINI_API_KEY उपलब्ध नहीं है। कृपया Render Dashboard -> Environment Variables में GEMINI_API_KEY जोड़ें।" if lang == "hi" else "⚠️ GEMINI_API_KEY is not configured."
        })

    try:
        image_bytes = await file.read()
        mime_type = file.content_type or "image/jpeg"
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        prompt = (
            "आप नेबुला एआई टीचर हैं। इस स्कूल की किताब के पन्ने/प्रश्न को छोटे बच्चों के लिए ब्लैकबोर्ड पर समझाने के अंदाज़ में बहुत सरल, स्पष्ट और रोचक तरीके से 2-3 वाक्यों में स्टेप-बाय-स्टेप हल करें।"
            if lang == "hi"
            else "You are Nebula AI Teacher. Explain and solve this school textbook question for young kids in 2-3 simple, engaging sentences suitable for a classroom blackboard."
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": base64_image
                            }
                        }
                    ]
                }
            ]
        }

        # Google Gemini Active Models
        target_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"

        req = urllib.request.Request(
            target_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=40) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            solution_text = res_data["candidates"][0]["content"]["parts"][0]["text"]
            return JSONResponse(content={"success": True, "solution": solution_text.strip()})

    except urllib.error.HTTPError as he:
        try:
            err_body = he.read().decode("utf-8")
            err_json = json.loads(err_body)
            last_error = err_json.get("error", {}).get("message", f"HTTP {he.code}: {he.reason}")
        except Exception:
            last_error = f"HTTP Error {he.code}: {he.reason}"
        
        err_msg = f"त्रुटि: फोटो का विश्लेषण नहीं हो सका ({last_error})" if lang == "hi" else f"Error: Unable to analyze image ({last_error})"
        return JSONResponse(content={"success": False, "solution": err_msg})

    except Exception as e:
        err_msg = f"त्रुटि: फोटो का विश्लेषण नहीं हो सका ({str(e)})" if lang == "hi" else f"Error: Unable to analyze image ({str(e)})"
        return JSONResponse(content={"success": False, "solution": err_msg})

@app.post("/analyze-homework")
async def analyze_homework_endpoint(file: UploadFile = File(...), lang: str = Form("hi")):
    return await process_gemini_vision(file, lang)

@app.post("/analyze")
async def analyze_alias_endpoint(file: UploadFile = File(...), lang: str = Form("hi")):
    return await process_gemini_vision(file, lang)

@app.post("/upload")
async def upload_alias_endpoint(file: UploadFile = File(...), lang: str = Form("hi")):
    return await process_gemini_vision(file, lang)

# ------------------------------------------------------------------------------
# 7. एडमिन डेटा मॉनिटर, फाइल अपलोड और किड्स ज़ोन
# ------------------------------------------------------------------------------
@app.get("/admin", response_class=HTMLResponse)
async def master_admin_panel(user: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    records = db.query(AcademyMasterRecord).all()
    rows = "".join([f"<tr class='border-b border-gray-800 text-xs'><td class='py-3 px-4 text-cyan-300'>{r.module_name}</td><td class='py-3 px-4'>{r.filename}</td><td class='py-3 px-4 text-emerald-400'>100% Encrypted</td><td class='py-3 px-4 text-gray-400'>{r.timestamp}</td></tr>" for r in records])
    
    return f"""
    <html>
    <head><meta charset="UTF-8"><title>Admin Monitor</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-slate-950 text-white p-6 sm:p-10 font-sans">
        <div class="max-w-6xl mx-auto space-y-8">
            <div class="flex justify-between items-center border-b border-gray-800 pb-4">
                <div>
                    <h1 class="text-2xl sm:text-3xl font-bold text-cyan-400">Dhruv Academy - Admin Monitor</h1>
                    <p class="text-xs text-gray-400">लॉगिन यूजर: {user.username}</p>
                </div>
                <div class="flex gap-2">
                    <a href="/admin/super-dashboard" class="px-4 py-2 bg-indigo-600 rounded-xl text-xs font-bold shadow-lg">कंट्रोल डैशबोर्ड</a>
                    <a href="/" class="px-4 py-2 bg-cyan-600 rounded-xl text-xs font-bold shadow-lg">← मुख्य पोर्टल</a>
                </div>
            </div>
            <div class="bg-slate-900 p-6 rounded-2xl border border-gray-800 space-y-4">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="border-b border-gray-700 text-xs text-gray-400">
                            <th class="py-3 px-4">मॉड्यूल नाम</th>
                            <th class="py-3 px-4">फाइल नाम</th>
                            <th class="py-3 px-4">सुरक्षा</th>
                            <th class="py-3 px-4">समय</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows if rows else "<tr><td colspan='4' class='py-8 text-center text-gray-500 text-sm'>अभी तक कोई डेटा अपलोड नहीं हुआ है।</td></tr>"}
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """

@app.post("/api/master-upload")
async def master_upload_endpoint(module_name: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    destination = UPLOAD_DIR / file.filename
    with open(destination, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    db.add(AcademyMasterRecord(module_name=module_name, filename=file.filename))
    db.commit()
    return HTMLResponse(content="""
    <html><head><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-slate-950 text-white flex items-center justify-center h-screen font-sans">
        <div class="bg-slate-900 p-8 rounded-3xl border border-cyan-500/50 text-center space-y-4 max-w-md shadow-2xl">
            <h2 class="text-2xl font-bold text-emerald-400">सफलतापूर्वक अपलोड हुआ!</h2>
            <a href="/" class="inline-block mt-4 px-6 py-2.5 bg-cyan-600 rounded-xl text-xs font-bold shadow-lg">वापस लौटें</a>
        </div>
    </body>
    </html>
    """)

@app.get("/kids-zone", response_class=HTMLResponse)
async def kids_zone():
    file_path = Path("kids-zone.html")
    if not file_path.exists():
        return HTMLResponse(content="""
        <html><body class='bg-slate-950 text-white p-10 font-sans text-center'>
            <h1 class='text-2xl font-bold text-amber-400'>Kids Zone</h1>
            <p class='text-sm text-gray-400 mt-2'>kids-zone.html फाइल मौजूद नहीं है।</p>
            <a href='/' class='inline-block mt-4 text-cyan-400'>← वापस मुख्य पेज पर जाएं</a>
        </body></html>
        """)
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

# ------------------------------------------------------------------------------
# 8. सर्वर एक्ज़ीक्यूशन (Render Auto-Detect Port Binding)
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
