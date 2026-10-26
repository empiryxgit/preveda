# syntax=docker/dockerfile:1
# Build from the project root:  docker build -f deploy/docker/Dockerfile -t preveda/madhu-dr:1.0.0 .
# ONE image for the Madhu-DR hospital-node service (FRD 4.1 / 10). Inference-only by default (small);
# build with  --build-arg WITH_TRAIN=true  to also include PyTorch so the same image can run training:
#   docker run --rm -v <dataset>:/dataset -v <work>:/work -e PREVEDA_DATA_DIR=/dataset -e PREVEDA_WORK_DIR=/work preveda/madhu-dr:train python -m training.train
FROM python:3.11-slim

ARG WITH_TRAIN=false
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
LABEL org.opencontainers.image.vendor="Empiryx" org.opencontainers.image.licenses="LicenseRef-Empiryx-Proprietary"

COPY requirements ./requirements
RUN pip install -r requirements/base.txt \
 && if [ "$WITH_TRAIN" = "true" ]; then pip install -r requirements/train.txt --extra-index-url https://download.pytorch.org/whl/cpu; fi

COPY src ./src
COPY training ./training
COPY config ./config
COPY LICENSE ./LICENSE
# Default signed model (registry + PUBLIC key only). Mount a volume on /models to deploy a newer one.
COPY models /models

RUN useradd --system --uid 10001 --no-create-home preveda && mkdir /data && chown preveda:preveda /data
USER preveda

ENV PYTHONPATH=/app/src:/app \
    PREVEDA_MODELS_DIR=/models \
    PREVEDA_GUIDELINES=/app/config/guidelines.json \
    PREVEDA_IMAGES_DIR=/images \
    PREVEDA_DATABASE_URL=sqlite:////data/madhu_dr.db
VOLUME /data
EXPOSE 8080 8081

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/ready').status==200 else 1)"

# One process, two listeners: REST API on 8080, web app on 8081 (both share one model and database).
CMD ["python", "-m", "preveda_dr.server"]
