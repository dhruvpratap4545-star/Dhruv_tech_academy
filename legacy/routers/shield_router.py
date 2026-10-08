from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

shield_router = APIRouter()
templates = Jinja2Templates(directory="templates")

@shield_router.get("/mobile-shield", response_class=HTMLResponse)
async def mobile_shield(request: Request):
    return templates.TemplateResponse("mobile-shield.html", {"request": request})
