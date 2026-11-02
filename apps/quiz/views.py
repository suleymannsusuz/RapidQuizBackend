from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.utils import client_ip, hash_ip

from . import services
from .serializers import (
    AnswerResponseSerializer,
    AnswerSerializer,
    QuestionResponseSerializer,
    ResultResponseSerializer,
    SessionCreatedSerializer,
    SessionCreateSerializer,
)
from .throttles import AnswerThrottle, QuestionThrottle, SessionStartThrottle

TOKEN_HEADER = "X-Session-Token"

token_parameter = OpenApiParameter(
    TOKEN_HEADER,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Oturum başlatılırken verilen gizli anahtar",
)


def session_token(request):
    return request.headers.get(TOKEN_HEADER, "")


class SessionCreateView(APIView):
    throttle_classes = [SessionStartThrottle]

    @extend_schema(
        request=SessionCreateSerializer,
        responses={201: SessionCreatedSerializer},
        summary="Yeni quiz oturumu başlatır",
    )
    def post(self, request):
        serializer = SessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session, token = services.start_session(
            category_slug=serializer.validated_data["category"],
            platform=serializer.validated_data["platform"],
            ip_hash=hash_ip(client_ip(request)),
        )
        category = session.category
        return Response(
            {
                "session_id": session.id,
                "session_token": token,
                "category": {"slug": category.slug, "name": category.name},
                "total_questions": services.QUESTIONS_PER_SESSION,
                "time_limit_ms": services.TIME_LIMIT_MS,
            },
            status=status.HTTP_201_CREATED,
        )


class QuestionView(APIView):
    throttle_classes = [QuestionThrottle]

    @extend_schema(
        parameters=[token_parameter],
        responses={200: QuestionResponseSerializer},
        summary="Sıradaki soruyu verir; ilk istekte süre başlar",
    )
    def get(self, request, session_id):
        return Response(services.serve_question(session_id, session_token(request)))


class AnswerView(APIView):
    throttle_classes = [AnswerThrottle]

    @extend_schema(
        parameters=[token_parameter],
        request=AnswerSerializer,
        responses={200: AnswerResponseSerializer},
        summary="Cevabı değerlendirir (choice_id=null: süre aşımı)",
    )
    def post(self, request, session_id):
        serializer = AnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.submit_answer(
            session_id,
            session_token(request),
            serializer.validated_data["question_id"],
            serializer.validated_data["choice_id"],
        )
        return Response(result)


class ResultView(APIView):
    throttle_classes = [QuestionThrottle]

    @extend_schema(
        parameters=[token_parameter],
        responses={200: ResultResponseSerializer},
        summary="Biten oturumun puan özeti",
    )
    def get(self, request, session_id):
        return Response(services.get_result(session_id, session_token(request)))
