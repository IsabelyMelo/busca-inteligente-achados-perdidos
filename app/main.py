from collections.abc import AsyncIterator
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from hmac import compare_digest
import logging
from math import ceil
from threading import Lock
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from sqlalchemy import create_engine

from app.config import Settings, get_settings
from app.matching import MatchingService
from app.repository import ItemRepository, MySQLItemRepository
from app.schemas import MatchItem, SearchRequest, SearchResponse

audit_logger = logging.getLogger("app.audit")
service_key_header = APIKeyHeader(name="X-Service-Key", auto_error=False)
audit_logger.setLevel(logging.INFO)
if not audit_logger.handlers:
    audit_handler = logging.StreamHandler()
    audit_handler.setFormatter(logging.Formatter("%(message)s"))
    audit_logger.addHandler(audit_handler)


class ServiceRateLimiter:
    """Janela deslizante local para a única credencial de serviço."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._requests: deque[float] = deque()
        self._lock = Lock()

    def allow(self, now: float) -> tuple[bool, int]:
        with self._lock:
            # Remove chamadas fora da janela de 60 segundos antes de aplicar o limite
            while self._requests and now - self._requests[0] >= 60:
                self._requests.popleft()
            if len(self._requests) >= self._limit:
                retry_after = max(1, ceil(60 - (now - self._requests[0])))
                return False, retry_after
            self._requests.append(now)
            return True, 0


def create_app(
    repository: ItemRepository | None = None,
    settings: Settings | None = None,
    *,
    include_category: bool = False,
) -> FastAPI:
    selected_settings = settings or get_settings()
    limiter = ServiceRateLimiter(selected_settings.rate_limit_per_minute)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # Cria o acesso ao banco apenas ao iniciar a aplicação, permitindo testes sem MySQL
        if selected_settings.service_api_key is None:
            raise RuntimeError("SERVICE_API_KEY deve ser configurada para iniciar a API")
        engine = None
        selected_repository = repository
        if selected_repository is None:
            engine = create_engine(
                selected_settings.database_url,
                pool_pre_ping=True,
                pool_recycle=1800,
                connect_args=selected_settings.database_connect_args,
            )
            selected_repository = MySQLItemRepository(engine)

        application.state.matching_service = MatchingService(
            selected_repository,
            method=selected_settings.match_method,
            alpha=selected_settings.match_alpha,
            beta=selected_settings.match_beta,
            include_category=include_category,
        )
        yield
        if engine is not None:
            engine.dispose()

    application = FastAPI(
        title="Busca Inteligente de Achados e Perdidos",
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.middleware("http")
    async def security_and_audit(request: Request, call_next):
        started_at = perf_counter()
        client = "anonymous"
        # Autentica e limita buscas antes de ler ou validar o corpo da requisição
        if request.method == "POST" and request.url.path == "/matches/search":
            configured_key = selected_settings.service_api_key
            supplied_key = request.headers.get("X-Service-Key", "")
            if configured_key is None or not compare_digest(
                supplied_key, configured_key.get_secret_value()
            ):
                response = JSONResponse(status_code=401, content={"detail": "Não autorizado"})
            else:
                client = "service"
                allowed, retry_after = limiter.allow(perf_counter())
                if not allowed:
                    response = JSONResponse(
                        status_code=429,
                        content={"detail": "Limite de requisições excedido"},
                        headers={"Retry-After": str(retry_after)},
                    )
                else:
                    response = await call_next(request)
        else:
            response = await call_next(request)

        # Registra metadados da requisição sem descrição ou credencial
        duration_ms = (perf_counter() - started_at) * 1000
        response.headers["X-Server-Time-Ms"] = f"{duration_ms:.6f}"
        route = (
            request.url.path
            if request.url.path in {"/health", "/matches/search"}
            else "other"
        )
        audit_logger.info(
            "timestamp=%s client=%s route=%s status=%s duration_ms=%.3f",
            datetime.now(timezone.utc).isoformat(),
            client,
            route,
            response.status_code,
            duration_ms,
        )
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _error: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": "Requisição inválida"})

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post(
        "/matches/search",
        response_model=SearchResponse,
        dependencies=[Security(service_key_header)],
    )
    def search(payload: SearchRequest, request: Request) -> SearchResponse:
        started_at = perf_counter()
        service: MatchingService = request.app.state.matching_service
        try:
            matches = service.search(payload.description, payload.top_k)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Descrição inválida") from error
        except Exception as error:
            # Esconde detalhes internos de falhas no banco ou no ranqueamento
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
