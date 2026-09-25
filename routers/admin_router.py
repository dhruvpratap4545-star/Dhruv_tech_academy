# -*- coding: utf-8 -*-
from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
import secrets
from database import get_db, AdminUser, AdminSession, RegisteredStudent

router = APIRouter(prefix="/admin", tags=["Admin"])

def get_current_admin(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    token = request.cookies.get("dhruv_auth_token")
    if not token:
        raise HTTPException(status_code=401, detail="सत्र समाप्त")
    sess = db.query(AdminSession).filter_by(session_token=token).first()
    if not sess:
        raise HTTPException(status_code=401, detail="अमान्य सत्र")
    user = db.query(AdminUser).filter_by(username=sess.username).first()
    if not user:
        raise HTTPException(status_code=401, detail="यूजर नहीं मिला")
    return user

def require_superadmin(user: AdminUser = Depends(get_current_admin)):
    if user.role != "superadmin":
        raise HTTPException(status_code=403, detail="अनुमति नहीं है")
    return user

@router.get("/super-master-panel", response_class=HTMLResponse)
def super_panel(user: AdminUser = Depends(require_superadmin), db: Session = Depends(get_db)):
    scount = db.query(RegisteredStudent).count()
    return f"""
    <!DOCTYPE html><html lang="hi"><head><meta charset="UTF-8"><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-slate-950 text-white p-6">
        <h1 class="text-2xl font-bold text-cyan-400">⚡ Super-Admin Command Center</h1>
        <p class="mt-4 text-gray-300">पंजीकृत छात्र: {scount}</p>
        <div class="mt-6"><a href="/" class="px-4 py-2 bg-slate-800 rounded-xl text-xs">🏠 मुख्य पोर्टल</a></div>
    </body></html>
    """
