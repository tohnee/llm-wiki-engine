.PHONY: up down logs ingest jwt eval test smoke fmt

up:                  ## 起本地全栈(pg+redis+minio+evidence+query)
	docker compose -f deploy/docker-compose.yml up -d --build

down:
	docker compose -f deploy/docker-compose.yml down

logs:
	docker compose -f deploy/docker-compose.yml logs -f

ingest:              ## make ingest MD=./sample.md TENANT=t1 DOC=doc1 DEPTH=D1
	python -m scripts.ingest_demo --tenant $(TENANT) --doc $(DOC) --md $(MD) --depth $(DEPTH)

jwt:                 ## make jwt TENANT=t1 USER=u1
	python -m scripts.issue_jwt --tenant $(TENANT) --user $(USER)

eval:                ## make eval DATA=./golden_qa.jsonl TENANT=t1
	python -m app.eval.harness $(DATA) $(TENANT)

smoke:               ## 离线冒烟测试(无需 DB/API),验证纯逻辑模块
	python -m tests.smoke

test: smoke
