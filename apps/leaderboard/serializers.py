from rest_framework import serializers

from apps.quiz.serializers import CategoryRefSerializer

from .validators import InvalidPlayerName, validate_player_name


class ScoreSubmitSerializer(serializers.Serializer):
    # Puan, doğru sayısı vb. istemciden alınmaz; fazladan gelen alanlar yok sayılır.
    player_name = serializers.CharField(max_length=100)

    def validate_player_name(self, value):
        try:
            return validate_player_name(value)
        except InvalidPlayerName as exc:
            raise serializers.ValidationError(str(exc)) from None


class LeaderboardQuerySerializer(serializers.Serializer):
    category = serializers.SlugField(max_length=50)


# Aşağıdakiler yalnızca OpenAPI şeması içindir.


class ScoreRowSerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    player_name = serializers.CharField()
    score = serializers.IntegerField()
    correct_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class ScoreSubmittedSerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    in_top_10 = serializers.BooleanField()
    score = serializers.IntegerField()
    leaderboard = ScoreRowSerializer(many=True)


class LeaderboardResponseSerializer(serializers.Serializer):
    category = CategoryRefSerializer()
    leaderboard = ScoreRowSerializer(many=True)
