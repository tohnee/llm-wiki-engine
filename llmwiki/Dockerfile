FROM docker.m.daocloud.io/python:3.11-slim

WORKDIR /srv
# 用清华 PyPI 镜像加速国内安装
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 默认走轻量依赖(配合 EMBED_MOCK=1 / EMBED API),不安装 torch+sentence-transformers
# 如需本地 bge-m3 模型,改 COPY requirements.txt 并允许下载 ~2.5GB
COPY requirements-light.txt .
RUN pip install --no-cache-dir -r requirements-light.txt

COPY app ./app
ENV PYTHONUNBUFFERED=1
