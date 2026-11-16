ARG STACKARR_BASE_IMAGE=python:3.13-slim
FROM ${STACKARR_BASE_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STACKARR_DATA=/var/lib/stackarr
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home stackarr
COPY pyproject.toml LICENSE ./
COPY stackarr ./stackarr
RUN pip install --no-cache-dir --no-deps . && mkdir -p /var/lib/stackarr && chown stackarr:stackarr /var/lib/stackarr
USER 10001:10001
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import os,urllib.request; r=urllib.request.Request('http://127.0.0.1:8787/healthz',headers={'Host':__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(os.environ.get('STACKARR_ORIGIN','http://localhost:8787')).netloc}); urllib.request.urlopen(r,timeout=3)"
CMD ["stackarr", "serve", "--host", "0.0.0.0"]
