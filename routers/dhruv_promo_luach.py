from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

shield_router = APIRouter()
templates = Jinja2Templates(directory="templates")

@shield_router.get("/launch", response_class=HTMLResponse)
async def promo_launch(request: Request):
    return templates.TemplateResponse("dhruv_promo_launch.html", {"request": request})
