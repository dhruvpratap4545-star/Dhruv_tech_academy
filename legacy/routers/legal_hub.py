from fastapi import APIRouter, Request

router = APIRouter()

@router.post("/api/legal-advice-solve")
async def legal_advice_solve(request: Request):
    return {"success": True, "advice": "लीगल हब राउट सक्रिय है।"}
