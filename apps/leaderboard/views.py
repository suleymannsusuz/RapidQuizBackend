from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.quiz.throttles import LeaderboardThrottle, ScoreThrottle
from apps.quiz.views import session_token, token_parameter

from . import services
from .serializers import (
    LeaderboardQuerySerializer,
    LeaderboardResponseSerializer,
    ScoreSubmitSerializer,
    ScoreSubmittedSerializer,
)


class ScoreSubmitView(APIView):
    throttle_classes = [ScoreThrottle]

    @extend_schema(
        parameters=[token_parameter],
        request=ScoreSubmitSerializer,
        responses={201: ScoreSubmittedSerializer},
        summary="Biten oturumun skorunu isimle kaydeder",
    )
    def post(self, request, session_id):
        serializer = ScoreSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.submit_score(
            session_id, session_token(request), serializer.validated_data["player_name"]
        )
        return Response(result, status=status.HTTP_201_CREATED)


class LeaderboardView(APIView):
    throttle_classes = [LeaderboardThrottle]

    @extend_schema(
        parameters=[
            OpenApiParameter("category", str, required=True, description="Kategori slug'ı")
        ],
        responses={200: LeaderboardResponseSerializer},
        summary="Kategorinin ilk 10 skoru",
    )
    def get(self, request):
        query = LeaderboardQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(services.get_leaderboard(query.validated_data["category"]))
