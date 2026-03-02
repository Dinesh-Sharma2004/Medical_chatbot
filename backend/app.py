import os
import uvicorn

if __name__ == "__main__":
    # Read port and host from env variables for flexibility
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("DEV_RELOAD", "false").lower() in ("1", "true", "yes")

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
