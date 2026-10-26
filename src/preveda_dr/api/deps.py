"""Shared FastAPI dependencies: things the lifespan put on app.state."""
from __future__ import annotations
from fastapi import HTTPException, Request
from ..ml.inference import Predictor
from ..persistence import Store


def get_predictor(request: Request) -> Predictor:
    p = request.app.state.predictor
    if p is None:
        raise HTTPException(503, f"model not available: {request.app.state.model_error}")
    return p


def get_store(request: Request) -> Store:
    return request.app.state.store


def get_guidelines(request: Request) -> dict:
    return request.app.state.guidelines
