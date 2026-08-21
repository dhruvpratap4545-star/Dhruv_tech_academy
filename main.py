#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from fastapi import FastAPI, Form, Request, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Dhruv Academy Master Ecosystem")

# एडमिन पासवर्ड और सेटिंग्स
ADMIN_PASSWORD = "dhruv123-secure-password-2026"

# फीचर्स और उनके पेड/फ्री होने का कंट्रोल (टिक-बॉक्स डेटा)
FEATURE_CONTROLS = {
    "kids_zone": {"name": "Kids Zone", "is_paid": False, "price": 0},
    "advanced_quiz": {"name": "Advanced Quiz", "is_paid": True, "price": 49},
    "ai_certificate": {"name": "AI Certificate Generator", "is_paid": True, "price": 99},
    "global_leaderboard": {"name": "Global Leaderboard", "is_paid": False, "price": 0}
}

# सब-एडमिन और उनकी परमिशन का डेटाबेस
SUB_ADMINS = {
    "finance_guy": {"password": "fin123password", "role": "finance_manager"},
    "support_guy": {"password": "sup123password", "role": "support_staff"}
}

@app.get("/", response_class=HTMLResponse)
def read_root():
    return """
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Dhruv Academy Master Ecosystem</title>
        <style>
            body { background: #0b0f19; color: #f8fafc; font-family: sans-serif; text-align: center; padding: 50px; }
            .container { background: #1e293b; padding: 40px; border-radius: 12px; display: inline-block; box-shadow: 0 10px 25px rgba(0,0,0,0.5); max-width: 600px; width: 100%; }
            h1 { color: #38bdf8; margin-bottom: 10px; font-size: 28px; }
            p { color: #94a3b8; font-size: 14px; margin-bottom: 30px; }
            .badge { background: #0284c7; color: #fff; padding: 8px 16px; border-radius: 20px; font-weight: bold; display: inline-block; margin-bottom: 20px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="badge">Dhruv Academy Master Ecosystem</div>
            <h1>नमस्ते, ध्रुव जी!</h1>
            <p>नर्सरी से लेकर आईएएस (IAS/PCS), पीसीएस और सभी प्रतियोगी परीक्षाओं के लिए भारत का सबसे उन्नत एआई पोर्टल।</p>
            <hr style="border:0; border-top:1px solid #334155; margin:20px 0;">
            <p style="font-size: 13px; color: #64748b;">© 2026 Dhruv Academy. All rights reserved.</p>
        </div>
    </body>
    </html>
    """

# फुटर के गुप्त लिंक से खुलने वाला लॉगिन पेज
@app.get("/secret-admin-login-dhruv", response_class=HTMLResponse)
def admin_login_page():
    return """
    <html>
    <head><title>Secure Portal Access</title></head>
    <body style="background:#0b0f19; color:#fff; font-family:sans-serif; display:flex; justify-content:center; align-items:center; height:100vh; margin:0;">
        <div style="background:#1e293b; padding:40px; border-radius:12px; box-shadow:0 10px 25px rgba(0,0,0,0.5); text-align:center; width:350px;">
            <h3 style="color:#38bdf8; margin-bottom:20px;">🔒 Corporate Access Control</h3>
            <form action="/secret-admin-login-dhruv" method="post">
                <input type="text" name="username" placeholder="Username / ID" required style="padding:12px; margin-bottom:10px; width:100%; background:#0b0f19; border:1px solid #475569; color:#fff; border-radius:6px; box-sizing:border-box;">
                <input type="password" name="password" placeholder="Password" required style="padding:12px; margin-bottom:15px; width:100%; background:#0b0f19; border:1px solid #475569; color:#fff; border-radius:6px; box-sizing:border-box;">
                <br>
                <button type="submit" style="padding:12px; width:100%; background:#0284c7; color:#fff; border:none; border-radius:6px; font-weight:bold; cursor:pointer;">Authenticate</button>
            </form>
            <br>
            <a href="/" style="color:#94a3b8; font-size:13px; text-decoration:none;">← Return to Home</a>
        </div>
    </body>
    </html>
    """

# लॉगिन सत्यापन और रोल-बेस्ड रिडायरेक्ट
@app.post("/secret-admin-login-dhruv")
def admin_login_verify(username: str = Form("admin"), password: str = Form(...)):
    if username == "admin" and password == ADMIN_PASSWORD:
        response = RedirectResponse(url="/secret-admin-dashboard-dhruv", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="dhruv_role", value="super_admin", httponly=True)
        return response
    
    if username in SUB_ADMINS and SUB_ADMINS[username]["password"] == password:
        role = SUB_ADMINS[username]["role"]
        response = RedirectResponse(url=f"/sub-admin-dashboard?role={role}", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="dhruv_role", value=role, httponly=True)
        return response

    return HTMLResponse("<body style='background:#0b0f19; color:#ff4d4d; text-align:center; padding-top:40vh; font-family:sans-serif;'><h2>❌ Access Denied: Invalid Credentials!</h2><p><a href='/secret-admin-login-dhruv' style='color:#fff;'>Try Again</a></p></body>", status_code=403)

# सुपर-एडमिन डैशबोर्ड (टिक-बॉक्स कंट्रोल के साथ)
@app.get("/secret-admin-dashboard-dhruv", response_class=HTMLResponse)
def super_admin_dashboard(request: Request):
    role = request.cookies.get("dhruv_role")
    if role != "super_admin":
        return RedirectResponse(url="/secret-admin-login-dhruv", status_code=status.HTTP_303_SEE_OTHER)
    
    features_html = ""
    for key, val in FEATURE_CONTROLS.items():
        checked = "checked" if val["is_paid"] else ""
        features_html += f"""
        <div style="background:#1e293b; padding:15px; margin-bottom:10px; border-radius:6px; display:flex; justify-content:space-between; align-items:center; border:1px solid #334155;">
            <span style="color:#f8fafc;"><b>{val['name']}</b> (Price: ₹{val['price']})</span>
            <form action="/toggle-feature" method="post" style="margin:0;">
                <input type="hidden" name="feature_key" value="{key}">
                <label style="color:#38bdf8; cursor:pointer;"><input type="checkbox" name="is_paid" {checked} onchange="this.form.submit()"> Paid Lock 🔒</label>
            </form>
        </div>
        """

    return f"""
    <html>
    <head><title>Dhruv Academy Admin Center</title></head>
    <body style="background:#0b0f19; padding:30px; font-family:sans-serif; color:#f8fafc;">
        <div style="background:#1e293b; padding:30px; border-radius:10px; box-shadow:0 4px 15px rgba(0,0,0,0.5); max-width:700px; margin:auto;">
            <h1 style="color:#38bdf8; margin-top:0;">नमस्ते, ध्रुव जी! 👋</h1>
            <p style="color:#94a3b8;">यह आपका Dhruv Academy Master Ecosystem का एडमिन कंट्रोल सेंटर है। यहाँ से आप तय करते हैं कौन सा फीचर फ्री रहेगा और किस पर पेड ताला लगेगा।</p>
            <hr style="border:0; border-top:1px solid #334155; margin:20px 0;">
            <h3 style="color:#f8fafc;">🛠️ फीचर टिक-बॉक्स कंट्रोल (Paywall Manager):</h3>
            {features_html}
            <br>
            <a href="/" style="color:#38bdf8; text-decoration:none; font-weight:bold;">← मुख्य वेबसाइट पर जाएं</a> | 
            <a href="/logout" style="color:#ef4444; text-decoration:none; font-weight:bold; float:right;">सुरक्षित लॉगआउट</a>
        </div>
    </body>
    </html>
    """

@app.post("/toggle-feature")
def toggle_feature(feature_key: str = Form(...), is_paid: Optional[str] = Form(None)):
    if feature_key in FEATURE_CONTROLS:
        FEATURE_CONTROLS[feature_key]["is_paid"] = True if is_paid else False
    return RedirectResponse(url="/secret-admin-dashboard-dhruv", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/sub-admin-dashboard", response_class=HTMLResponse)
def sub_admin_dashboard(role: str, request: Request):
    cookie_role = request.cookies.get("dhruv_role")
    if cookie_role not in ["finance_manager", "support_staff"]:
        return RedirectResponse(url="/secret-admin-login-dhruv", status_code=status.HTTP_303_SEE_OTHER)
    
    panel_title = "Finance & Payment Dashboard" if role == "finance_manager" else "Student Support Dashboard"
    
    return f"""
    <html>
    <head><title>{panel_title}</title></head>
    <body style="background:#0b0f19; padding:30px; font-family:sans-serif; color:#f8fafc;">
        <div style="background:#1e293b; padding:30px; border-radius:10px; box-shadow:0 4px 15px rgba(0,0,0,0.5); max-width:600px; margin:auto;">
            <h2 style="color:#38bdf8;">👥 Sub-Admin Portal ({role})</h2>
            <p style="color:#94a3b8;">आपको केवल आपके तय किए गए कार्य क्षेत्र की परमिशन दी गई है।</p>
            <hr style="border:0; border-top:1px solid #334155; margin:20px 0;">
            <a href="/logout" style="color:#ef4444; text-decoration:none; font-weight:bold;">लॉगआउट करें</a>
        </div>
    </body>
    </html>
    """

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/secret-admin-login-dhruv", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="dhruv_role")
    return response
