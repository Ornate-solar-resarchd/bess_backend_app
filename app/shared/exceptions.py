from __future__ import annotations

from fastapi import HTTPException, status


class APINotFoundException(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class APIConflictException(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class APIForbiddenException(HTTPException):
    def __init__(self, detail: str = "Forbidden") -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class APIValidationException(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class BESSNotFoundException(APINotFoundException):
    def __init__(self, bess_unit_id: int) -> None:
        super().__init__(detail=f"BESS unit {bess_unit_id} not found")


class InvalidStageTransitionException(APIValidationException):
    def __init__(self, from_stage: object, to_stage: object) -> None:
        super().__init__(detail=f"Invalid transition from {from_stage} to {to_stage}")


class ChecklistIncompleteException(APIConflictException):
    def __init__(self, pending_items: list[str]) -> None:
        super().__init__(
            detail={
                "message": "Mandatory checklist items are incomplete",
                "pending_items": pending_items,
            }
        )


class EngineerNotAvailableException(APINotFoundException):
    def __init__(self) -> None:
        super().__init__(detail="No engineer available for assignment")
