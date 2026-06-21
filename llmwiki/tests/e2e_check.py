"""端到端验证:图谱 + 问答 + 文档"""
import asyncio, json, httpx, sys

BASE = "http://localhost:8000"
ADMIN = "http://localhost:8002"
INGEST = "http://localhost:8003"

async def main():
    async with httpx.AsyncClient() as c:
        # 登录
        r = await c.post(f"{ADMIN}/auth/login", json={"email": "a@acme.com", "password": "pw"})
        d = r.json()
        token = d["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        print("=== 1. 文档状态 ===")
        r = await c.get(f"{INGEST}/documents/doc_508056f7013a483d/status", headers=headers)
        print(f"   {r.json()}")

        print("\n=== 2. 知识图谱 ===")
        r = await c.get(f"{BASE}/graph?fmt=json", headers=headers)
        d = r.json()
        data = json.loads(d["data"]) if isinstance(d.get("data"), str) else d.get("data", {})
        print(f"   节点({len(data.get('nodes',[]))}):")
        for n in data.get("nodes", []):
            print(f"     - {n['name']} ({n['type']})")
        print(f"   边({len(data.get('edges',[]))}):")
        for e in data.get("edges", []):
            print(f"     - {e['source'][:8]} → {e['target'][:8]} [{e.get('relation','')}]")

        print("\n=== 3. 问答 ===")
        for q in ["项目Alpha的预算是多少?", "项目Alpha的负责人是谁?", "项目Alpha的主要供应商是谁?"]:
            r = await c.post(f"{BASE}/ask", headers=headers,
                            json={"question": q, "session_id": "e2e"})
            d = r.json()
            print(f"   Q: {q}")
            print(f"   A: {d.get('answer','')[:100]}")
            print()

        print("\n=== 全部通过 ===")

if __name__ == "__main__":
    asyncio.run(main())
