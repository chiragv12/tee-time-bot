from fastapi import APIRouter, Response, status

from app.models import BookNowRequest, BookNowResult
from app.services.booking_engine import book_now

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("/book-now", response_model=BookNowResult)
async def book_now_endpoint(request: BookNowRequest, response: Response) -> BookNowResult:
    """Attempt a booking immediately, for manual testing against real searches."""
    result = await book_now(request)
    if not result.success:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return result
