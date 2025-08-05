from fastapi import HTTPException, status, Path
from typing import Optional
from stremio_addon.core.config import settings

async def verify_password(password: Optional[str] = None):
    """
    A FastAPI dependency that checks for a password if one is configured.
    This function will be applied to both protected and unprotected routes.
    """
    # If a password is required by the configuration...
    if settings.addon_password:
        # ...and the user did not provide one in the URL...
        if password is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This addon requires a password in the URL.",
            )
        # ...or if the password provided is incorrect...
        if password != settings.addon_password:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid password provided.",
            )

    # If no password is required or the correct one was provided, allow access.
    return


