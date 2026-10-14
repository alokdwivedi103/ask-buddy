from fastapi import Header, HTTPException, Depends
from config import Settings

settings = Settings()

async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != settings.API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return x_api_key
