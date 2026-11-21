# Build from the repository root; supply an approved Python 3.12 image@sha256.
ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE}
COPY pyproject.toml /opt/auton/pyproject.toml
COPY src /opt/auton/src
COPY containers/local-runtime/requirements.txt /opt/auton/runtime-requirements.txt
RUN python -m pip install --no-cache-dir /opt/auton -r /opt/auton/runtime-requirements.txt
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/tmp/hf HOME=/tmp
USER 65534:65534
WORKDIR /tmp
ENTRYPOINT ["python", "-m", "auton.model.runtime_worker", "--config", "/runtime/config.json"]
