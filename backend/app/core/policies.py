from app.core.rate_limiter import Policy, Scope

LOGIN = Policy("login", capacity=5, refill_per_second=1 / 60, scope=Scope.IP)
REGISTER = Policy("register", capacity=3, refill_per_second=3 / 3600, scope=Scope.IP)
# Five times the per-/64 budget: a /48 absorbs five fully active subscribers before it binds, and
# an attacker holding one gets 5x a single client instead of 65,536x. IPv4 keys as-is here, so
# the stricter per-IP policy always refuses first and IPv4 clients never notice this one.
LOGIN_PREFIX = Policy("login_prefix", capacity=25, refill_per_second=5 / 60, scope=Scope.IP_PREFIX)
REGISTER_PREFIX = Policy(
    "register_prefix", capacity=15, refill_per_second=15 / 3600, scope=Scope.IP_PREFIX
)
# Failed sign-ins only (a success refunds), across every IP, so a distributed guesser gets at most
# 10 + 240 a day per account. A browser that already signed in to the account spends its own
# LOGIN_DEVICE bucket instead, so flooding LOGIN_ACCOUNT cannot lock the owner out of it.
LOGIN_ACCOUNT = Policy(
    "login_account", capacity=10, refill_per_second=10 / 3600, scope=Scope.ACCOUNT
)
LOGIN_DEVICE = Policy("login_device", capacity=10, refill_per_second=10 / 3600, scope=Scope.ACCOUNT)
# Both span all IPs: attempts caps 409 email probing and is never refunded; REGISTER_GLOBAL caps
# created accounts and is refunded when a registration fails.
REGISTER_ATTEMPTS_GLOBAL = Policy(
    "register_attempts_global", capacity=200, refill_per_second=200 / 3600, scope=Scope.GLOBAL
)
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
