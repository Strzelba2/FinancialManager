from pydantic import BaseModel, EmailStr


class SessionUser(BaseModel):
    username: str
    first_name: str
    email: EmailStr
