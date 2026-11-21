# Supply an approved Python 3.12 image pinned by @sha256; no implicit platform selection.
ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE}
COPY requirements.txt /opt/auton/requirements.txt
RUN python -m pip install --no-cache-dir -r /opt/auton/requirements.txt
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/tmp/hf HOME=/tmp
USER 65534:65534
WORKDIR /tmp
ENTRYPOINT ["python", "-I", "/worker.py", "/input/manifest.json"]
