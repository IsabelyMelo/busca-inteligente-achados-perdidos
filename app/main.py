from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import create_engine

from app.config import Settings, get_settings
from app.matching import MatchingService
from app.repository import ItemRepository, MySQLItemRepository
from app.schemas import MatchItem, SearchRequest, SearchResponse


def create_app(
    repository: ItemRepository | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    selected_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = None
        selected_repository = repository
        if selected_repository is None:
            engine = create_engine(
                selected_settings.database_url,
                pool_pre_ping=True,
                pool_recycle=1800,
            )
            selected_repository = MySQLItemRepository(engine)

        application.state.matching_service = MatchingService(
            selected_repository,
            alpha=selected_settings.match_alpha,
            beta=selected_settings.match_beta,
        )
        yield
        if engine is not None:
            engine.dispose()

    application = FastAPI(
        title="Busca Inteligente de Achados e Perdidos",
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/matches/search", response_model=SearchResponse)
    def search(payload: SearchRequest, request: Request) -> SearchResponse:
        started_at = perf_counter()
        service: MatchingService = request.app.state.matching_service
        try:
            matches = service.search(payload.description, payload.top_k)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(
                status_code=503,
                detail="Não foi possível consultar os itens encontrados",
            ) from error

        elapsed_ms = (perf_counter() - started_at) * 1000
        response_matches = [MatchItem.from_ranked_item(item) for item in matches]
        return SearchResponse(
            returned_count=len(response_matches),
            processing_time_ms=round(elapsed_ms, 3),
            matches=response_matches,
        )

    return application


app = create_app()
