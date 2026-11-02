from rest_framework.throttling import SimpleRateThrottle


class IPRateThrottle(SimpleRateThrottle):
    """IP başına sayaç; oranlar settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] içinde."""

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class SessionStartThrottle(IPRateThrottle):
    scope = "session_start"


class AnswerThrottle(IPRateThrottle):
    scope = "answer"


class QuestionThrottle(IPRateThrottle):
    scope = "question"


class ScoreThrottle(IPRateThrottle):
    scope = "score"


class LeaderboardThrottle(IPRateThrottle):
    scope = "leaderboard"
