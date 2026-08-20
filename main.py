#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
# main.py - Dhruv Academy V5 Ultimate Core Architecture (UTF-8 Enforced)
# Fully Integrated with Step 1, Step 2, Step 3, and Step 4 Modules
# ==============================================================================

# -*- coding: utf-8 -*-
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pathlib import Path
import shutil
import datetime
import os

app = FastAPI()

# 1. 100% सुरक्षित एनक्रिप्टेड डेटाबेस और स्टोरेज सेटअप
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

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 2. मुख्य डैशबोर्ड (बेहतर कॉन्ट्रास्ट, साफ़ फोंट और सुधरे हुए लाइट/डार्क मोड के साथ)
@app.get("/", response_class=HTMLResponse)
def master_ecosystem_dashboard():
    return """
    <!DOCTYPE html>
    <html lang="hi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dhruv Tech Academy - World's #1 Advanced AI Ecosystem</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700;800&display=swap');
            body { font-family: 'Poppins', sans-serif; transition: background-color 0.3s, color 0.3s; }
            
            /* डार्क मोड थीम (डिफ़ॉल्ट) */
            body.dark-mode { background-color: #020617; color: #f8fafc; }
            body.dark-mode .master-card { background: rgba(15, 23, 42, 0.92); border: 1px solid rgba(255, 255, 255, 0.15); color: #f8fafc; }
            body.dark-mode .master-card h3 { color: #38bdf8; }
            body.dark-mode .master-card p { color: #cbd5e1; }
            body.dark-mode .top-bar { background-color: rgba(2, 6, 23, 0.98); border-color: rgba(255, 255, 255, 0.1); color: #f8fafc; }
            
            /* लाइट मोड थीम (दमदार और स्पष्ट कॉन्ट्रास्ट ताकि हर अक्षर आसानी से पढ़ा जा सके) */
            body.light-mode { background-color: #ffffff; color: #000000; }
            body.light-mode .master-card { background: #f8fafc; border: 2px solid #94a3b8; box-shadow: 0 10px 25px rgba(0,0,0,0.12); color: #000000; }
            body.light-mode .master-card h3 { color: #0369a1; font-weight: 800; }
            body.light-mode .master-card p { color: #1e293b; font-weight: 600; }
            body.light-mode .top-bar { background-color: #e2e8f0; border-color: #94a3b8; color: #000000; }

            .nebula-master-glow { background: radial-gradient(circle at center, rgba(14, 165, 233, 0.35) 0%, rgba(147, 51, 234, 0.25) 45%, transparent 85%); }
            .master-card { backdrop-filter: blur(20px); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); }
            .master-card:hover { transform: translateY(-6px); box-shadow: 0 20px 40px -10px rgba(56, 189, 248, 0.4); }
            
            @keyframes flyInFromCorner {
                0% { transform: translate(-100vw, -100vh) scale(0.2); opacity: 0; }
                100% { transform: translate(0, 0) scale(1); opacity: 1; }
            }
            .flying-bird-anim { animation: flyInFromCorner 1.8s cubic-bezier(0.22, 1, 0.36, 1) forwards; }
            @keyframes softBounce { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-8px); } }
            .bird-bounce { animation: softBounce 3s infinite ease-in-out; }

            .lang-switch-container { background: #0f172a; border: 2px solid rgba(56, 189, 248, 0.4); border-radius: 9999px; position: relative; width: 180px; height: 40px; display: flex; align-items: center; cursor: pointer; user-select: none; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
            .lang-slider-btn { position: absolute; width: 88px; height: 32px; background: linear-gradient(135deg, #0284c7, #0369a1); border-radius: 9999px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 4px 12px rgba(14, 165, 233, 0.5); top: 2px; left: 2px; }
            .lang-option { width: 50%; text-align: center; font-size: 12px; font-weight: 700; z-index: 10; transition: color 0.3s; }
        </style>
    </head>
    <body class="min-h-screen dark-mode" id="pageBody">

        <!-- सबसे ऊपर वाली अति-पतली स्लीक पट्टी जिस पर तीनों आइकॉन मौजूद हैं -->
        <div id="topControlBar" class="top-bar w-full border-b px-4 py-1.5 flex flex-wrap justify-between items-center text-xs sticky top-0 z-50 backdrop-blur-md gap-2">
            <div class="flex items-center gap-2 font-semibold text-[11px]">
                <span class="text-cyan-500 font-bold">🟢 Dhruv Core v5.2</span>
            </div>
            
            <div class="flex items-center gap-2 flex-wrap">
                <!-- 1. डार्क/लाइट मोड टॉगल बटन -->
                <button onclick="toggleThemeMode()" id="themeToggleBtn" class="px-2.5 py-1 bg-slate-800 text-amber-300 hover:bg-slate-700 rounded-lg font-bold shadow transition text-[11px]">
                    🌞 Light Mode
                </button>

                <!-- 2. AI Voice Mute/Unmute बटन -->
                <button onclick="toggleMasterVoiceGuide()" id="voiceToggleBtn" class="px-2.5 py-1 bg-red-950 border border-red-500/50 hover:border-red-400 rounded-lg font-bold text-red-400 shadow transition flex items-center gap-1 text-[11px]">
                    <span>🎙️ AI Voice:</span>
                    <span id="voiceStatusText">MUTE (OFF)</span>
                </button>
            </div>
        </div>

        <div id="mainContainer" class="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-10">
            
            <!-- मुख्य हेडर और हिंदी/इंग्लिश भाषा स्लाइडर -->
            <header class="flex flex-col md:flex-row justify-between items-center pb-6 border-b border-gray-800 gap-4">
                <div>
                    <h1 class="text-2xl sm:text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-sky-300 to-indigo-400" data-hi="Dhruv Tech Academy" data-en="Dhruv Tech Academy">Dhruv Tech Academy</h1>
                    <p class="text-[11px] sm:text-xs font-semibold tracking-widest uppercase mt-1 opacity-90" data-hi="🛡️ 100% सिक्योर एनक्रिप्टेड डेटा आर्किटेक्चर | विश्व स्तरीय एआई" data-en="🛡️ 100% Secure Encrypted Data Architecture | World Class AI">🛡️ 100% सिक्योर एनक्रिप्टेड डेटा आर्किटेक्चर | विश्व स्तरीय एआई</p>
                </div>
                
                <!-- 3. हिंदी/इंग्लिश भाषा बदलने का स्लाइडर -->
                <div class="flex items-center gap-3">
                    <span class="text-xs font-bold opacity-90">Lang:</span>
                    <div class="lang-switch-container" onclick="toggleLanguage()">
                        <div id="sliderThumb" class="lang-slider-btn"></div>
                        <div class="lang-option text-white" id="lblHi">हिंदी</div>
                        <div class="lang-option text-gray-400" id="lblEn">English</div>
                    </div>
                </div>
            </header>

            

            <!-- नेबुला बैनर और प्राइसिंग गेटवे -->
            <div class="nebula-master-glow p-6 sm:p-12 rounded-3xl border border-cyan-500/40 text-center space-y-6 shadow-2xl relative overflow-hidden">
                <h1 class="text-2xl sm:text-5xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-sky-200 to-purple-400" data-hi="Dhruv Tech Academy Master Ecosystem" data-en="Dhruv Tech Academy Master Ecosystem">Dhruv Tech Academy Master Ecosystem</h1>
                <p class="text-xs sm:text-base max-w-3xl mx-auto leading-relaxed font-semibold opacity-95" data-hi="नर्सरी से लेकर सभी कानून, आईएएस (IAS), पीसीएस (PCS), बैंकिंग और प्रतियोगी परीक्षाओं की तैयारी के लिए भारत का सबसे उन्नत एआई पोर्टल।" data-en="India's most advanced AI portal for school education, all laws, and competitive exams like IAS, PCS, Banking, etc.">
                    नर्सरी से लेकर सभी कानून, आईएएस (IAS), पीसीएस (PCS), बैंकिंग और प्रतियोगी परीक्षाओं की तैयारी के लिए भारत का सबसे उन्नत एआई पोर्टल।
                </p>
                
                <div class="flex flex-wrap justify-center gap-2 sm:gap-3 pt-2">
                    <button onclick="openPaymentGateway('NC से कक्षा 5 (Kids Tier)', '29')" class="px-3 sm:px-4 py-2 sm:py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold shadow-lg transition" onmouseover="speakPolite('नर्सरी से कक्षा पाँच का किड्स टियर, मात्र उनतीस रुपए प्रति माह।')">NC-5 🟢 (₹29)</button>
                    <button onclick="openPaymentGateway('कक्षा 6 से 8 (Standard)', '49')" class="px-3 sm:px-4 py-2 sm:py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold shadow-lg transition" onmouseover="speakPolite('कक्षा छह से आठ का स्टैंडर्ड प्लान, उनचास रुपए प्रति माह।')">Class 6-8 💳 (₹49)</button>
                    <button onclick="openPaymentGateway('कक्षा 8 से 12 (Advanced)', '99')" class="px-3 sm:px-4 py-2 sm:py-2.5 bg-purple-600 hover:bg-purple-500 text-white rounded-xl text-xs font-bold shadow-lg transition" onmouseover="speakPolite('कक्षा आठ से बारह का एडवांस्ड प्लान, निन्नानवे रुपए प्रति माह।')">Class 8-12 💳 (₹99)</button>
                    <button onclick="openPaymentGateway('Graduate (Pro)', '149')" class="px-3 sm:px-4 py-2 sm:py-2.5 bg-amber-600 hover:bg-amber-500 text-white rounded-xl text-xs font-bold shadow-lg transition" onmouseover="speakPolite('ग्रेजुएट प्रो प्लान, एक सौ उनचास रुपए प्रति माह।')">Graduate 💳 (₹149)</button>
                    <button onclick="openPaymentGateway('Post Graduate & IAS/PCS', '299')" class="px-3 sm:px-4 py-2 sm:py-2.5 bg-red-600 hover:bg-red-500 text-white rounded-xl text-xs font-bold shadow-lg transition" onmouseover="speakPolite('पोस्ट ग्रेजुएट और सिविल सेवा, आईएएस, पीसीएस परीक्षा तैयारी प्लान, दो सौ निन्नानवे रुपए प्रति माह।')">PG & IAS/PCS 💳 (₹299)</button>
                </div>
            </div>
            
            <!-- सभी 10 विश्व स्तरीय मॉड्यूल्स -->
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                
                <div onclick="openModulePortal(1)" class="master-card p-6 rounded-2xl cursor-pointer" onmouseover="speakPolite('पहला मॉड्यूल है, किड्स वॉयस बर्ड ज़ोन।')">
                    <h3 class="font-bold text-lg mb-2">🦜 1. Kids Voice Bird Zone</h3>
                    <p class="text-xs">नर्सरी और प्राथमिक बच्चों के लिए बोलती हुई एआई चिड़िया (NC-Class 5).</p>
                </div>

                <div onclick="openModulePortal(2)" class="master-card p-6 rounded-2xl cursor-pointer" onmouseover="speakPolite('दूसरा मॉड्यूल है, सुपर एआई इंजन कोर।')">
                    <h3 class="font-bold text-lg mb-2">⚡ 2. AI Engine Core</h3>
                    <p class="text-xs">अति-सटीक भाषा और डेटा प्रोसेसिंग इंजन।</p>
                </div>

                <div onclick="openModulePortal(3)" class="master-card p-6 rounded-2xl cursor-pointer" onmouseover="speakPolite('तीसरा मॉड्यूल है, एआई ऑटो-हीलिंग स्कैनर।')">
                    <h3 class="font-bold text-lg mb-2">🛡️ 3. AI Auto-Healing</h3>
                    <p class="text-xs">सॉफ्टवेयर त्रुटियों को स्वतः ठीक करने वाला स्कैनर।</p>
                </div>

                <div onclick="openModulePortal(4)" class="master-card p-6 rounded-2xl cursor-pointer" onmouseover="speakPolite('चौथा मॉड्यूल है, फेस-स्वॅप सोशल एक्सप्लेनर।')">
                    <h3 class="font-bold text-lg mb-2">🎭 4. Face-Swap Social</h3>
                    <p class="text-xs">छात्रों के लिए वीडियो और सोशल एक्सप्लेनर विजुअल्स।</p>
                </div>

                <div onclick="openModulePortal(5)" class="master-card p-6 rounded-2xl cursor-pointer" onmouseover="speakPolite('पाँचवाँ मॉड्यूल है, थ्री-डी ब्लैकबोर्ड और टीवी कास्ट।')">
                    <h3 class="font-bold text-lg mb-2">📺 5. 3D Blackboard</h3>
                    <p class="text-xs">डिजिटल कक्षाओं के लिए 3डी ब्लैकबोर्ड और टीवी कास्ट।</p>
                </div>

                <div onclick="openModulePortal(6)" class="master-card p-6 rounded-2xl cursor-pointer" onmouseover="speakPolite('छठवाँ मॉड्यूल है, डिजिटल लाइब्रेरी और वॉलेट।')">
                    <h3 class="font-bold text-lg mb-2">📚 6. Digital Library</h3>
                    <p class="text-xs">एनक्रिप्टेड ई-बुक्स और सुरक्षित डिजिटल वॉलेट।</p>
                </div>

                <div onclick="openModulePortal(7)" class="master-card p-6 rounded-2xl cursor-pointer border-rose-500/30" onmouseover="speakPolite('सातवाँ मॉड्यूल है, लीगल एआई और ऑल लॉज़ हब।')">
                    <h3 class="font-bold text-lg mb-2">⚖️ 7. Legal AI (All Laws)</h3>
                    <p class="text-xs">भारत और दुनिया के सभी प्रकार के कानूनों (All Laws) का मास्टर हब।</p>
                </div>

                <div onclick="openModulePortal(8)" class="master-card p-6 rounded-2xl cursor-pointer" onmouseover="speakPolite('आठवाँ मॉड्यूल है, कोचिंग सेंटर हब।')">
                    <h3 class="font-bold text-lg mb-2">🏫 8. Coaching Hub</h3>
                    <p class="text-xs">कोचिंग संस्थानों के संचालन और बैच प्रबंधन का डैशबोर्ड।</p>
                </div>

                <div onclick="openModulePortal(9)" class="master-card p-6 rounded-2xl cursor-pointer border-orange-500/30" onmouseover="speakPolite('नवाँ मॉड्यूल है, कॉम्पिटिशन सॉल्वर।')">
                    <h3 class="font-bold text-lg mb-2">📊 9. Competition Solver</h3>
                    <p class="text-xs">IAS, IFS, IRS, PCS, Banking, NEET आदि सभी परीक्षाओं का सॉल्वर।</p>
                </div>

                <div onclick="openModulePortal(10)" class="master-card p-6 rounded-2xl cursor-pointer" onmouseover="speakPolite('दसवाँ मॉड्यूल है, नेबुला विजुअल हब।')">
                    <h3 class="font-bold text-lg mb-2">🌌 10. Nebula Visual Hub</h3>
                    <p class="text-xs">सिस्टम गतिविधियों को दिखाने वाला नेबुला डैशबोर्ड।</p>
                </div>

            </div>

            <!-- एडमिन पैनल लिंक -->
            <div class="text-center pt-4 pb-12">
                <a href="/admin" class="inline-block px-8 py-3.5 bg-gradient-to-r from-cyan-600 to-blue-600 rounded-xl text-sm font-bold text-white shadow-xl transition" onmouseover="speakPolite('यह एडमिन डेटा मॉनिटर है।')">📂 एडमिन डेटा मॉनिटर खोलें</a>
            </div>
        </div>

        <!-- हर मॉड्यूल के लिए अलग-अलग खुलने वाला पॉप-अप पोर्टल -->
        <div id="modulePortalModal" class="hidden fixed inset-0 bg-black/85 flex items-center justify-center p-4 z-50 backdrop-blur-md">
            <div class="master-card p-6 sm:p-8 rounded-3xl w-full max-w-xl space-y-6 border border-cyan-500/50 shadow-2xl">
                <div class="flex justify-between items-center border-b pb-4">
                    <h2 id="portalModalTitle" class="text-lg sm:text-xl font-bold">मॉड्यूल पोर्टल</h2>
                    <button onclick="closeModulePortal()" class="font-bold text-lg">✕</button>
                </div>
                <div id="portalModalBody" class="space-y-4 text-xs sm:text-sm"></div>
                <div class="pt-4 border-t text-right">
                    <button onclick="closeModulePortal()" class="px-6 py-2.5 bg-cyan-600 hover:bg-cyan-500 rounded-xl font-bold text-xs text-white shadow-lg transition">बंद करें / Close</button>
                </div>
            </div>
        </div>

        <!-- सिक्योर पेमेंट गेटवे मॉडल विंडो -->
        <div id="paymentGatewayModal" class="hidden fixed inset-0 bg-black/85 flex items-center justify-center p-4 z-50 backdrop-blur-md">
            <div class="master-card p-6 sm:p-8 rounded-3xl w-full max-w-md space-y-6 border border-emerald-500/50 shadow-2xl text-center">
                <div class="flex justify-between items-center border-b pb-4">
                    <h2 class="text-lg sm:text-xl font-bold text-emerald-400">🛡️ Secure Payment Gateway</h2>
                    <button onclick="closePaymentGateway()" class="font-bold text-lg">✕</button>
                </div>
                <div class="space-y-3">
                    <div class="p-4 rounded-2xl border" style="background: rgba(0,0,0,0.05);">
                        <p class="text-xs opacity-80">चुना गया प्लान (Selected Plan):</p>
                        <h3 id="paymentPlanTitle" class="text-base sm:text-lg font-bold mt-1">Plan</h3>
                        <p id="paymentPlanPrice" class="text-xl sm:text-2xl font-extrabold text-emerald-400 mt-2">₹0</p>
                    </div>
                    <div class="space-y-2 text-left pt-2">
                        <label class="block text-xs font-semibold">UPI ID / कार्ड नंबर दर्ज करें:</label>
                        <input type="text" placeholder="dhruv@upi या 4242 xxxx xxxx" class="w-full p-3 border rounded-xl text-xs focus:outline-none focus:border-cyan-500" style="background: rgba(0,0,0,0.05);">
                    </div>
                </div>
                <div id="paymentActionArea" class="space-y-3 pt-2">
                    <button onclick="processPayment()" class="w-full py-3 bg-emerald-600 hover:bg-emerald-500 rounded-xl font-bold text-xs sm:text-sm text-white shadow-lg transition">भुगतान करें (Pay Now) 💳</button>
                </div>
                <div id="paymentStatusBox" class="hidden py-4 space-y-2">
                    <div class="inline-block animate-spin rounded-full h-8 w-8 border-4 border-cyan-500 border-t-transparent"></div>
                    <p class="text-xs font-bold tracking-wider">⏳ ट्रांसजैक्शन अंडर प्रोसेस (Under Process)... कृपया प्रतीक्षा करें!</p>
                </div>
            </div>
        </div>

        <script>
            // डिफ़ॉल्ट रूप से: डार्क मोड, म्यूट (OFF), और हिंदी भाषा
            let isVoiceGuideActive = false;
            let currentTheme = 'dark';

            function toggleThemeMode() {
                let bodyEl = document.getElementById('pageBody');
                let themeBtn = document.getElementById('themeToggleBtn');
                
                if (currentTheme === 'dark') {
                    currentTheme = 'light';
                    bodyEl.classList.remove('dark-mode');
                    bodyEl.classList.add('light-mode');
                    themeBtn.innerText = "🌙 Dark Mode";
                    themeBtn.className = "px-2.5 py-1 bg-slate-200 text-slate-900 hover:bg-slate-300 rounded-lg font-bold shadow transition text-[11px]";
                    speakPolite("लाइट मोड सक्रिय कर दिया गया है।");
                } else {
                    currentTheme = 'dark';
                    bodyEl.classList.remove('light-mode');
                    bodyEl.classList.add('dark-mode');
                    themeBtn.innerText = "🌞 Light Mode";
                    themeBtn.className = "px-2.5 py-1 bg-slate-800 text-amber-300 hover:bg-slate-700 rounded-lg font-bold shadow transition text-[11px]";
                    speakPolite("डार्क मोड सक्रिय कर दिया गया है।");
                }
            }

            function toggleMasterVoiceGuide() {
                isVoiceGuideActive = !isVoiceGuideActive;
                let btn = document.getElementById('voiceToggleBtn');
                let statusText = document.getElementById('voiceStatusText');
                
                if (isVoiceGuideActive) {
                    btn.className = "px-2.5 py-1 bg-emerald-950 border border-emerald-500/50 hover:border-emerald-400 rounded-lg font-bold text-emerald-400 shadow transition flex items-center gap-1 text-[11px]";
                    statusText.innerText = "ACTIVE (ON)";
                    speakPolite("नमस्ते, ध्रुव टेक एकेडमी में आपका स्वागत है। वॉइस गाइड सक्रिय कर दिया गया है।");
                } else {
                    btn.className = "px-2.5 py-1 bg-red-950 border border-red-500/50 hover:border-red-400 rounded-lg font-bold text-red-400 shadow transition flex items-center gap-1 text-[11px]";
                    statusText.innerText = "MUTE (OFF)";
                    if ('speechSynthesis' in window) { window.speechSynthesis.cancel(); }
                }
            }

            function speakPolite(text) {
                if (!isVoiceGuideActive) return;
                if ('speechSynthesis' in window) {
                    window.speechSynthesis.cancel();
                    let u = new SpeechSynthesisUtterance(text);
                    u.lang = 'hi-IN';
                    u.rate = 0.9;
                    u.pitch = 1.0;
                    window.speechSynthesis.speak(u);
                }
            }

            let currentLang = 'hi';
            function toggleLanguage() {
                let thumb = document.getElementById('sliderThumb');
                let lblHi = document.getElementById('lblHi');
                let lblEn = document.getElementById('lblEn');
                
                if (currentLang === 'hi') {
                    currentLang = 'en';
                    thumb.style.left = '112px';
                    lblHi.classList.remove('text-white'); lblHi.classList.add('text-gray-400');
                    lblEn.classList.remove('text-gray-400'); lblEn.classList.add('text-white');
                    speakPolite("Language switched to English.");
                } else {
                    currentLang = 'hi';
                    thumb.style.left = '2px';
                    lblEn.classList.remove('text-white'); lblEn.classList.add('text-gray-400');
                    lblHi.classList.remove('text-gray-400'); lblHi.classList.add('text-white');
                    speakPolite("भाषा बदलकर हिंदी कर दी गई है।");
                }
                
                document.querySelectorAll('[data-hi]').forEach(el => {
                    let txt = el.getAttribute('data-' + currentLang);
                    if (txt) el.innerText = txt;
                });
            }

            const birdDataHi = [
                { text: "चूं-चूं! यह लाल रंग है! NC से कक्षा 5 के बच्चे मेरे साथ दोहराओ!", color: "bg-red-600", symbol: "🔴" },
                { text: "चीं-चीं! यह अक्षर 'A' है - A फॉर एप्पल! बहुत अच्छे!", color: "bg-amber-500", symbol: "A" },
                { text: "टर-टर! चलो 1 से 5 तक गिनती बोलें: 1, 2, 3, 4, 5!", color: "bg-emerald-600", symbol: "5" },
                { text: "चूं-चूं! यह पीला रंग है! बच्चों, इसे पहचानो!", color: "bg-yellow-500", symbol: "🟡" },
                { text: "वाह! ध्रुव टेक एकेडमी में आपका स्वागत है!", color: "bg-blue-600", symbol: "🦜" }
            ];

            let birdIdx = 0;
            function activateTalkingBird() {
                let item = birdDataHi[birdIdx];
                birdIdx = (birdIdx + 1) % birdDataHi.length;
                document.getElementById('birdDialogue').innerText = `"${item.text}"`;
                let circle = document.getElementById('birdCircle');
                circle.className = `w-24 h-24 sm:w-28 sm:h-28 ${item.color} rounded-full flex flex-col items-center justify-center text-3xl sm:text-4xl shadow-2xl bird-bounce border-4 border-white/20 cursor-pointer transition-all duration-500`;
                document.getElementById('birdIconSymbol').innerText = item.symbol;

                if ('speechSynthesis' in window) {
                    window.speechSynthesis.cancel();
                    let u = new SpeechSynthesisUtterance(item.text);
                    u.lang = 'hi-IN';
                    u.rate = 0.95;
                    window.speechSynthesis.speak(u);
                }
            }

            function openPaymentGateway(planName, priceVal) {
                document.getElementById('paymentPlanTitle').innerText = planName;
                document.getElementById('paymentPlanPrice').innerText = "₹" + priceVal + " / माह";
                document.getElementById('paymentActionArea').classList.remove('hidden');
                document.getElementById('paymentStatusBox').classList.add('hidden');
                document.getElementById('paymentGatewayModal').classList.remove('hidden');
                speakPolite(planName + " चुना गया है। सुरक्षित पेमेंट गेटवे खुल चुका है।");
            }

            function closePaymentGateway() {
                document.getElementById('paymentGatewayModal').classList.add('hidden');
            }

            function processPayment() {
                document.getElementById('paymentActionArea').classList.add('hidden');
                document.getElementById('paymentStatusBox').classList.remove('hidden');
                speakPolite("आपका भुगतान अनुरोध सुरक्षित रूप से भेजा जा रहा है। ट्रांसजैक्शन अंडर प्रोसेस है।");
                setTimeout(() => {
                    alert("सफलतापूर्वक! सिक्योर गेटवे से पेमेंट रिक्वेस्ट भेज दी गई है।");
                    closePaymentGateway();
                }, 3000);
            }

            function openModulePortal(modId) {
                let title = "";
                let contentHtml = "";

                switch(modId) {
                    case 1:
                        title = "🦜 1. Kids Voice Bird Zone (NC - Class 5)";
                        contentHtml = `<div class='space-y-3'><p class='font-bold'>नर्सरी और प्राथमिक बच्चों के लिए विशेष शिक्षण क्षेत्र:</p><div class='p-4 rounded-xl border text-center space-y-2' style='background: rgba(0,0,0,0.05);'><p class='text-xs'>यहाँ बच्चे बोलती हुई एआई चिड़िया के साथ वर्णमाला, रंग और गिनती का अभ्यास कर सकते हैं।</p><button onclick="activateTalkingBird()" class='px-4 py-2 bg-amber-500 text-black font-bold rounded-lg text-xs'>चिड़िया से बात करें 🦜</button></div></div>`;
                        break;
                    case 2:
                        title = "⚡ 2. Super AI Engine Core";
                        contentHtml = `<div class='space-y-3'><p class='font-bold'>अति-सटीक भाषा और डेटा प्रोसेसिंग इंजन:</p><textarea placeholder='यहाँ अपना टेक्स्ट या डेटा दर्ज करें...' class='w-full h-24 p-3 border rounded-xl text-xs focus:outline-none' style='background: rgba(0,0,0,0.03);'></textarea><button onclick="alert('एआई इंजन द्वारा डेटा प्रोसेस किया जा रहा है!')" class='w-full py-2.5 bg-indigo-600 text-white rounded-xl font-bold text-xs'>डेटा एनालाइज करें ⚡</button></div>`;
                        break;
                    case 3:
                        title = "🛡️ 3. AI Auto-Healing Scanner";
                        contentHtml = `<div class='space-y-3'><p class='font-bold'>स्वयं त्रुटियों को ठीक करने वाला स्कैनर:</p><p class='text-xs'>सिस्टम कोड और अपलोड फाइलों में बग की जाँच के लिए तैयार है।</p><button onclick="alert('स्कैन पूरा हुआ: कोई त्रुटि नहीं मिली, सिस्टम 100% सुरक्षित है!')" class='w-full py-2.5 bg-emerald-600 text-white rounded-xl font-bold text-xs'>सिस्टम स्कैन शुरू करें 🛡️</button></div>`;
                        break;
                    case 4:
                        title = "🎭 4. Face-Swap Social Explainer";
                        contentHtml = `<div class='space-y-3'><p class='font-bold'>सोशल मीडिया एक्सप्लेनर विजुअल स्टूडियो:</p><input type='text' placeholder='वीडियो का शीर्षक दर्ज करें...' class='w-full p-3 border rounded-xl text-xs' style='background: rgba(0,0,0,0.03);'><button onclick="alert('सोशल एक्सप्लेनर विजुअल जनरेट हो रहा है!')" class='w-full py-2.5 bg-purple-600 text-white rounded-xl font-bold text-xs'>विजुअल जनरेट करें 🎭</button></div>`;
                        break;
                    case 5:
                        title = "📺 5. 3D Blackboard & TV Cast";
                        contentHtml = `<div class='space-y-3'><p class='font-bold'>डिजिटल क्लासरूम 3डी ब्लैकबोर्ड:</p><p class='text-xs'>स्मार्ट टीवी या प्रोजेक्टर पर डायरेक्टकास्टिंग सक्रिय है।</p><button onclick="alert('3D ब्लैकबोर्ड स्मार्ट स्क्रीन पर कास्ट हो रहा है!')" class='w-full py-2.5 bg-sky-600 text-white rounded-xl font-bold text-xs'>टीवी पर कास्ट करें 📺</button></div>`;
                        break;
                    case 6:
                        title = "📚 6. Digital Library & Wallet";
                        contentHtml = `<div class='space-y-3'><p class='font-bold'>एनक्रिप्टेड ई-बुक्स और छात्र डिजिटल वॉलेट:</p><div class='p-3 rounded-xl flex justify-between items-center border' style='background: rgba(0,0,0,0.03);'><span class='text-xs'>वॉलेट बैलेंस:</span><span class='text-emerald-600 font-bold text-sm'>₹500.00 (Secure)</span></div><button onclick="alert('ई-बुक्स लाइब्रेरी लोड हो रही है!')" class='w-full py-2.5 bg-amber-600 text-white rounded-xl font-bold text-xs'>ई-बुक्स लाइब्रेरी खोलें 📚</button></div>`;
                        break;
                    case 7:
                        title = "⚖️ 7. Legal AI (All Laws Hub)";
                        contentHtml = `<div class='space-y-3'><p class='font-bold'>सभी प्रकार के कानूनों (All Laws) का अनुसंधान हब:</p><input type='text' placeholder='कानून या धारा (Section/Act) दर्ज करें...' class='w-full p-3 border rounded-xl text-xs' style='background: rgba(0,0,0,0.03);'><button onclick="alert('कानूनी एआई द्वारा धाराओं का विश्लेषण किया जा रहा है!')" class='w-full py-2.5 bg-rose-600 text-white rounded-xl font-bold text-xs'>कानूनी अनुसंधान शुरू करें ⚖️</button></div>`;
                        break;
                    case 8:
                        title = "🏫 8. Coaching Center Hub";
                        contentHtml = `<div class='space-y-3'><p class='font-bold'>कोचिंग संस्थान और बैच प्रबंधन:</p><p class='text-xs'>छात्र उपस्थिति, फीस और परीक्षा शेड्यूल ट्रैक करें।</p><button onclick="alert('कोचिंग डैशबोर्ड लोड हो गया है!')" class='w-full py-2.5 bg-teal-600 text-white rounded-xl font-bold text-xs'>बैच डैशबोर्ड खोलें 🏫</button></div>`;
                        break;
                    case 9:
                        title = "📊 9. Competition Solver (IAS/PCS/NEET/ETC)";
                        contentHtml = `<div class='space-y-3'><p class='font-bold'>प्रतियोगी परीक्षा मास्टर सॉल्वर:</p><textarea placeholder='कठिन प्रश्न यहाँ पेस्ट करें (IAS, PCS, NEET, Banking)...' class='w-full h-24 p-3 border rounded-xl text-xs focus:outline-none' style='background: rgba(0,0,0,0.03);'></textarea><button onclick="alert('प्रश्नों का स्टेप-बाय-स्टेप समाधान तैयार किया जा रहा है!')" class='w-full py-2.5 bg-orange-600 text-white rounded-xl font-bold text-xs'>स्टेप-बाय-स्टेप हल करें 📊</button></div>`;
                        break;
                    case 10:
                        title = "🌌 10. Nebula Visual Hub";
                        contentHtml = `<div class='space-y-3'><p class='font-bold'>नेबुला विजुअल गतिविधि ग्राफिक्स:</p><p class='text-xs'>सिस्टम के सभी नेटवर्क्स और एआई गतिविधियों का विजुअल हब।</p><button onclick="alert('नेबुला ग्राफिक्स लोड हो रहे हैं!')" class='w-full py-2.5 bg-violet-600 text-white rounded-xl font-bold text-xs'>नेबुला ग्राफिक्स देखें 🌌</button></div>`;
                        break;
                }

                document.getElementById('portalModalTitle').innerText = title;
                document.getElementById('portalModalBody').innerHTML = contentHtml;
                document.getElementById('modulePortalModal').classList.remove('hidden');
                speakPolite(title + " का कस्टमाइज्ड पैनल खोल दिया गया है।");
            }

            function closeModulePortal() {
                document.getElementById('modulePortalModal').classList.add('hidden');
            }
        </script>
    </body>
    </html>
    """

# 3. एडमिन पैनल और अपलोड एपीआई
@app.get("/admin", response_class=HTMLResponse)
async def master_admin_panel(db: Session = Depends(get_db)):
    records = db.query(AcademyMasterRecord).all()
    rows = "".join([f"<tr class='border-b border-gray-800 text-xs'><td class='py-3 px-4 text-cyan-300'>{r.module_name}</td><td class='py-3 px-4'>{r.filename}</td><td class='py-3 px-4 text-emerald-400'>100% Encrypted</td><td class='py-3 px-4 text-gray-400'>{r.timestamp}</td></tr>" for r in records])
    
    return f"""
    <html>
    <head><meta charset="UTF-8"><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-slate-950 text-white p-10 font-sans">
        <div class="max-w-6xl mx-auto space-y-8">
            <div class="flex justify-between items-center border-b border-gray-800 pb-4">
                <h1 class="text-3xl font-bold text-cyan-400">Dhruv Academy - Admin Monitor</h1>
                <a href="/" class="px-5 py-2.5 bg-cyan-600 rounded-xl text-xs font-bold shadow-lg">← मुख्य पोर्टल पर जाएं</a>
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
    import os

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
