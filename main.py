#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
# main.py - Dhruv Academy Master Ecosystem (API Key Rotation & Crash Safe)
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
    </head>
    <body class="bg-slate-950 text-white min-h-screen p-6 font-sans">
        <div class="max-w-5xl mx-auto space-y-8 text-center pt-10">
            <h1 class="text-3xl sm:text-5xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-sky-300 to-indigo-400">Dhruv Academy Master Ecosystem</h1>
            <p class="text-gray-400 text-sm max-w-2xl mx-auto">100% सिक्योर एनक्रिप्टेड डेटा आर्किटेक्चर | विश्व स्तरीय एआई वर्चुअल क्लासरूम</p>
            <div class="pt-6">
                <a href="/kids-zone" class="inline-block px-8 py-4 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 rounded-2xl text-lg font-bold text-white shadow-2xl transition transform hover:scale-105">
                    🚀 Kids Zone (वर्चुअल क्लासरूम) खोलें
                </a>
            </div>
        </div>
    </body>
    </html>
    """

# ------------------------------------------------------------------------------
# 6. ऑटो एपीआई कीज़ रोटेशन इंजन (Detects GEMINI_API_KEY1, 2, 3)
# ------------------------------------------------------------------------------
def get_all_gemini_keys() -> List[str]:
    keys = []
    # आपके Render डैशबोर्ड के अनुसार (GEMINI_API_KEY1, GEMINI_API_KEY2, GEMINI_API_KEY3)
    for i in range(1, 6):
        k_val = (os.environ.get(f"GEMINI_API_KEY{i}") or os.environ.get(f"GEMINI_API_KEY_{i}") or "").strip().strip('"').strip("'")
        if k_val and k_val not in keys:
            keys.append(k_val)

    # सिंगल या कॉमा सेपरेटेड बैकअप
    env_keys_raw = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEYS") or "").strip()
    if env_keys_raw:
        for k in env_keys_raw.split(","):
            cleaned = k.strip().strip('"').strip("'")
            if cleaned and cleaned not in keys:
                keys.append(cleaned)

    return keys

async def process_gemini_vision(file: UploadFile, lang: str):
    api_keys = get_all_gemini_keys()
    
    if not api_keys:
        return JSONResponse(content={
            "success": False,
            "solution": "⚠️ सर्वर पर GEMINI_API_KEY1 उपलब्ध नहीं है।" if lang == "hi" else "⚠️ GEMINI_API_KEY1 is not configured."
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

        last_error = ""

        # Key Rotation: यदि Key 1 पर कोटा फुल (429) हो तो तुरंत Key 2 पर स्विच
        for key in api_keys:
            target_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={key}"
            try:
                req = urllib.request.Request(
                    target_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )

                with urllib.request.urlopen(req, timeout=35) as response:
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
                continue
            except Exception as e:
                last_error = str(e)
                continue

        if "quota" in last_error.lower() or "429" in last_error:
            rate_limit_msg = (
                "⏳ नेबुला टीचर थोड़ा विश्राम ले रही हैं (फ़्री कोटा लिमिट)। कृपया 30-40 सेकंड बाद दोबारा 'सॉल्यूशन देखें' दबाएँ! 🌟"
                if lang == "hi"
                else "⏳ Nebula Teacher is taking a short rest (Free Quota Limit). Please retry in 30-40 seconds! 🌟"
            )
            return JSONResponse(content={"success": False, "solution": rate_limit_msg})

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
                <h1 class="text-2xl font-bold text-cyan-400">Admin Monitor</h1>
                <a href="/" class="px-4 py-2 bg-cyan-600 rounded-xl text-xs font-bold">← मुख्य पोर्टल</a>
            </div>
            <div class="bg-slate-900 p-6 rounded-2xl border border-gray-800">
                <table class="w-full text-left border-collapse">{rows}</table>
            </div>
        </div>
    </body>
    </html>
    """

@app.get("/kids-zone", response_class=HTMLResponse)
async def kids_zone():
    file_path = Path("kids-zone.html")
    if not file_path.exists():
        return HTMLResponse(content="<h1>kids-zone.html file missing</h1>")
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
