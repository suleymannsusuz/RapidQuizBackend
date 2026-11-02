from rest_framework import serializers

from .models import QuizSession

MAX_BIGINT = 2**63 - 1


class SessionCreateSerializer(serializers.Serializer):
    category = serializers.SlugField(max_length=50)
    platform = serializers.ChoiceField(choices=QuizSession.Platform.choices, default="web")


class AnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    # Süre dolunca istemci null gönderir; alan yine de zorunludur.
    choice_id = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, allow_null=True)


# Aşağıdakiler yalnızca OpenAPI şeması içindir; yanıtlar services.py'den düz sözlük döner.


class CategoryRefSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()


class SessionCreatedSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    session_token = serializers.CharField(
        help_text="Gizli anahtar; sonraki isteklerde X-Session-Token"
    )
    category = CategoryRefSerializer()
    total_questions = serializers.IntegerField()
    time_limit_ms = serializers.IntegerField()


class QuestionRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    text = serializers.CharField()


class ChoiceRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    text = serializers.CharField()


class QuestionResponseSerializer(serializers.Serializer):
    position = serializers.IntegerField()
    total_questions = serializers.IntegerField()
    question = QuestionRefSerializer()
    choices = ChoiceRefSerializer(many=True)
    time_limit_ms = serializers.IntegerField()
    remaining_ms = serializers.IntegerField()
    current_score = serializers.IntegerField()


class AnswerResponseSerializer(serializers.Serializer):
    is_correct = serializers.BooleanField()
    correct_choice_id = serializers.IntegerField()
    points = serializers.IntegerField()
    total_score = serializers.IntegerField()
    timed_out = serializers.BooleanField()
    is_last = serializers.BooleanField()


class ResultResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=QuizSession.Status.choices)
    category = CategoryRefSerializer()
    total_questions = serializers.IntegerField()
    total_score = serializers.IntegerField()
    correct_count = serializers.IntegerField()
    total_response_ms = serializers.IntegerField()
