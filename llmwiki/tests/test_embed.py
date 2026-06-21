"""测试 Embedding API 连通性(使用 .env 中的配置)。"""
import asyncio
import os
import sys
sys.path.insert(0, ".")

# 不强制设置任何 env,使用 .env 中的 LLM provider 配置
os.environ.setdefault("EMBED_MOCK", "0")

from app.llm.embed import embed


async def test():
    texts = ["项目Alpha的总预算为800万元", "项目Alpha的负责人是李四", "Hello world test"]
    print(f"=== embedding {len(texts)} texts ===", flush=True)
    from app.llm.embed import _EMBED_BASE_URL, _EMBED_API_KEY, _EMBED_MODEL
    print(f"  base_url={_EMBED_BASE_URL}", flush=True)
    print(f"  model={_EMBED_MODEL}", flush=True)
    print(f"  api_key={'set' if _EMBED_API_KEY else 'empty'}", flush=True)
    try:
        vecs = await embed(texts)
        print(f"result count: {len(vecs)}", flush=True)
        for i, v in enumerate(vecs):
            non_zero = any(x != 0 for x in v)
            print(f"  [{i}] dim={len(v)}, first 5 values: {v[:5]}, non_zero={non_zero}", flush=True)
        print("=== SUCCESS ===", flush=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FAILED: {e}", flush=True)

if __name__ == "__main__":
    asyncio.run(test())
