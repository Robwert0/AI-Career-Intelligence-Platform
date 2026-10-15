from app.core.rate_limiter import Policy, Scope

LOGIN = Policy("login", capacity=5, refill_per_second=1 / 60, scope=Scope.IP)
REGISTER = Policy("register", capacity=3, refill_per_second=3 / 3600, scope=Scope.IP)
# All IPs combined: rotating proxies multiply REGISTER, never this.
REGISTER_GLOBAL = Policy(
    "register_global", capacity=20, refill_per_second=20 / 3600, scope=Scope.GLOBAL
)
REFRESH = Policy("refresh", capacity=10, refill_per_second=10 / 60, scope=Scope.IP)
LOGOUT = Policy("logout", capacity=10, refill_per_second=10 / 60, scope=Scope.IP)
ME_IP = Policy("me_ip", capacity=120, refill_per_second=2.0, scope=Scope.IP)
ME_USER = Policy("me_user", capacity=60, refill_per_second=1.0, scope=Scope.USER)
ADMIN_IP = Policy("admin_ip", capacity=60, refill_per_second=1.0, scope=Scope.IP)
ADMIN_USER = Policy("admin_user", capacity=30, refill_per_second=0.5, scope=Scope.USER)
CHAT_USER = Policy("chat_user", capacity=20, refill_per_second=20 / 60, scope=Scope.USER)
CHAT_USER_DAILY = Policy(
    "chat_user_daily", capacity=200, refill_per_second=200 / 86400, scope=Scope.USER
)
CHAT_IP = Policy("chat_ip", capacity=30, refill_per_second=0.5, scope=Scope.IP)
MATCH_JOB_USER = Policy(
    "match_job_user", capacity=20, refill_per_second=20 / 3600, scope=Scope.USER
)
# One intake is at most two extraction calls; 30 a day covers eight analyses plus re-pastes.
MATCH_JOB_USER_DAILY = Policy(
    "match_job_user_daily", capacity=30, refill_per_second=30 / 86400, scope=Scope.USER
)
MATCH_POLL_IP = Policy("match_poll_ip", capacity=120, refill_per_second=2.0, scope=Scope.IP)
MATCH_POLL_USER = Policy("match_poll_user", capacity=60, refill_per_second=1.0, scope=Scope.USER)
MATCH_ANALYSIS_USER = Policy(
    "match_analysis_user", capacity=5, refill_per_second=5 / 3600, scope=Scope.USER
)
# One analysis is up to ~20 model calls (~$0.06 worst case at the default prices): eight a day
# lets one account take at most ~40% of the analysis pool.
MATCH_ANALYSIS_USER_DAILY = Policy(
    "match_analysis_user_daily", capacity=8, refill_per_second=8 / 86400, scope=Scope.USER
)
# A continue finishes an analysis its submit or retry already paid for, and each of those pauses
# at most once. Twice the analysis cap leaves room for a refused (404/409/503) continue to be
# clicked again without locking a paid-for analysis out.
MATCH_CONTINUE_USER_DAILY = Policy(
    "match_continue_user_daily", capacity=16, refill_per_second=16 / 86400, scope=Scope.USER
)
