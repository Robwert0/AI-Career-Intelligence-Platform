from app.core.rate_limiter import Policy, Scope

LOGIN = Policy("login", capacity=5, refill_per_second=1 / 60, scope=Scope.IP)
REGISTER = Policy("register", capacity=3, refill_per_second=3 / 3600, scope=Scope.IP)
REFRESH = Policy("refresh", capacity=10, refill_per_second=10 / 60, scope=Scope.IP)
ME_IP = Policy("me_ip", capacity=120, refill_per_second=2.0, scope=Scope.IP)
ME_USER = Policy("me_user", capacity=60, refill_per_second=1.0, scope=Scope.USER)
