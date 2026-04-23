from fastapi import APIRouter
from app.services.llm_chat import check_llm_connectivity

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/healthz/llm")
def healthz_llm() -> dict[str, str | bool]:
    return check_llm_connectivity()
