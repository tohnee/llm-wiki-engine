"""直接检索测试"""
import asyncio, json, httpx, hmac, time

BASE = "http://localhost:8001"
ADMIN = "http://localhost:8002"

def sign(tenant_id, user_id, session_id, secret="dev-internal-secret"):
    ts = int(time.time())
    payload = f"{tenant_id}:{user_id}:{session_id}:{ts}"
    sig = hmac.new(secret.encode(), payload.encode(), "sha256").hexdigest()
    return f"{tenant_id}:{user_id}:{session_id}:{ts}:{sig}"

async def main():
    async with httpx.AsyncClient() as c:
        # login
        r = await c.post(f"{ADMIN}/auth/login", json={"email": "a@acme.com", "password": "pw"})
        token = r.json()["access_token"]

        # 1. test graph
        print("=== 图谱 ===")
        r = await c.get("http://localhost:8000/graph?fmt=json", headers={"Authorization": f"Bearer {token}"})
        d = r.json()
        data = json.loads(d["data"])
        print(f"  nodes: {len(data['nodes'])}, edges: {len(data['edges'])}")
        for n in data["nodes"]:
            print(f"    {n['name']} ({n['type']})")

        # 2. test search directly on evidence
        print("\n=== 证据检索(直接调用 evidence) ===")
        ih = sign("t1", "admin", "search-test")
        r = await c.post(f"{BASE}/search", json={"query": "项目Alpha的预算"},
                         headers={"x-internal-auth": ih})
        d = r.json()
        print(f"  tier: {d.get('tier')}")
        spans = d.get("results") or d.get("spans") or []
        print(f"  spans: {len(spans)}")
        for s in spans[:5]:
            print(f"    [{s.get('document_id','?')[-8:]}:{s.get('span_id','?')[-8:]}] {s.get('content','')[:80]}")

        # 3. test ask
        print("\n=== 问答 ===")
        r = await c.post("http://localhost:8000/ask", json={"question": "项目Alpha的预算是多少?", "session_id": "final-test"},
                         headers={"Authorization": f"Bearer {token}"}, timeout=300)
        d = r.json()
        print(f"  answer: {d.get('answer','')[:200]}")
        print(f"  ratio: {d.get('verified_ratio')}")

        print("\n=== 完成 ===")

if __name__ == "__main__":
    asyncio.run(main())
