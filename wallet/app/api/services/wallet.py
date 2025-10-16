from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.schamas.schemas import WalletCreate
from app.schamas.response import WalletResponse
from app.utils.utils import normalize_name
from app.crud.wallet_crud import (
    ensure_unique_name, create_wallet, get_wallet, delete_wallet
    )


async def create_wallet_service(session: AsyncSession, data: WalletCreate) -> WalletResponse:
    """
    Create a new wallet for a given user.

    Args:
        session (AsyncSession): SQLAlchemy async session.
        data (WalletCreate): Wallet creation data including user_id and name.

    Returns:
        WalletResponse: The created wallet's ID and normalized name.

    Raises:
        ValueError: If name is empty or too long.
        HTTPException: If the name is not unique for the user.
    """
    
    name = normalize_name(data.name)
    if not name:
        raise ValueError("Wallet name cannot be empty.")
    if len(name) > 40:
        raise ValueError("Wallet name is too long (max 40 characters).")
    
    user_id = data.user_id
    
    await ensure_unique_name(session, user_id, name)
    
    data = WalletCreate(name=name, user_id=user_id)
    
    wallet = await create_wallet(session, data)
    
    return WalletResponse(id=wallet.id, name=wallet.name)


async def delete_wallet_service(
    session: AsyncSession, 
    wallet_id: uuid.UUID, 
    user_id: uuid.UUID, 
) -> bool:
    """
    Delete a wallet by ID if it belongs to the given user.

    Args:
        session (AsyncSession): SQLAlchemy async session.
        wallet_id (UUID): The wallet ID to delete.
        user_id (UUID): The user ID attempting the deletion.

    Returns:
        bool: True if wallet was deleted, False if not found or not authorized.
    """
    wallet = await get_wallet(session, wallet_id)
    
    if not wallet:
        return False
    if wallet.user_id != user_id:  
        return False
    return await delete_wallet(session, wallet_id)