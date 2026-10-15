from fastapi import APIRouter
import database as db

router = APIRouter(prefix="/api/diagnostics", tags=["System Diagnostic Tools"])

@router.get("/status")
async def check_system_health():
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row["name"] for row in cursor.fetchall()]
        conn.close()
        
        # Self-healing if essential database elements go missing unexpectedly
        required_tables = ["users", "drawings", "logs"]
        healed_actions = []
        
        for table in required_tables:
            if table not in tables:
                db.init_db()
                healed_actions.append(f"Recreated missing table: {table}")
                db.log_event("WARN", f"Self-healed missing table component: {table}")
        
        return {
            "status": "healthy",
            "database": "connected",
            "detected_tables": tables,
            "healed_actions": healed_actions if healed_actions else "None. Database structure is perfect."
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "recommendation": "Ensure read/write permissions on the dhruv_academy.db file."
        }