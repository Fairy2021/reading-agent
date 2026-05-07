from fastapi import APIRouter

from app.api.routes import agent, books, chat, health, media

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(books.router, prefix="/books", tags=["books"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
api_router.include_router(media.router, tags=["media"])
