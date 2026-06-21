"""签发测试 JWT。 用法: python -m scripts.issue_jwt --tenant t1 --user u1"""
import argparse
import os
import time
import jwt

ap = argparse.ArgumentParser()
ap.add_argument("--tenant", required=True)
ap.add_argument("--user", required=True)
args = ap.parse_args()

token = jwt.encode(
    {"tenant_id": args.tenant, "sub": args.user, "iat": int(time.time()),
     "exp": int(time.time()) + 3600},
    os.getenv("JWT_SECRET", "dev-jwt-secret"), algorithm="HS256")
print(token)
