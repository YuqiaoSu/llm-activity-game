from fastapi import APIRouter, Request, HTTPException
from services.place_service.service import get_place, list_places

router = APIRouter()


@router.get("")
def get_places(request: Request) -> list[dict]:
    db = request.app.state.db
    places = list_places(db)
    return [p.model_dump() for p in places]


@router.get("/{place_id}")
def get_place_by_id(place_id: str, request: Request) -> dict:
    db = request.app.state.db
    place = get_place(db, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return place.model_dump()
