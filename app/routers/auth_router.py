from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
from app.utils.auth import create_token

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(data: LoginRequest):
    if (
        data.username != os.getenv("ADMIN_USERNAME")
        or data.password != os.getenv("ADMIN_PASSWORD")
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token()
    return {"access_token": token}
