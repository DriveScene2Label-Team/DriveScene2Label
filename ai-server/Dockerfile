FROM python:3.12-slim-bookworm
ARG VESPA_REF=acb2b6e8683363795528f049fe0444ef9f3efdb9
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/models/huggingface TORCH_HOME=/models/torch \
    VESPA_ROOT=/opt/vespa VESPA_PYTHON=/opt/vespa-env/bin/python VESPA_OUTPUT_ROOT=/results \
    NUSCENES_ROOT=/data/nuscenes CLIP_IMAGE_ROOT=/data/nuscenes VESPA_DATA_ROOT=/data/nuscenes \
    RECORDING_OUTPUT_ROOT=/recordings
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential libgl1 libgomp1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY ai-server/requirements.txt /tmp/clip.txt
RUN pip install -r /tmp/clip.txt
# Pinned upstream commit + DriveScene2Label patches (ai-server/vespa-patches, same script as the Colab notebook).
COPY ai-server/vespa-patches/ /tmp/vespa-patches/
RUN git clone https://github.com/TUMFTM/VESPA.git /opt/vespa && git -C /opt/vespa checkout "$VESPA_REF" \
    && bash /tmp/vespa-patches/apply.sh /opt/vespa "$VESPA_REF"
COPY ai-server/requirements-vespa.txt /tmp/vespa.txt
# Share large PyTorch libraries, override only VESPA's older scientific dependencies.
RUN python -m venv --system-site-packages /opt/vespa-env && /opt/vespa-env/bin/pip install -r /tmp/vespa.txt
RUN cd /opt/vespa && /opt/vespa-env/bin/python -c "import main_pseudo_vlm; import main_pseudo_union"
# SSH client for VESPA_EXECUTOR=ssh (remote Slurm). Separate layer keeps the heavy layers above cached.
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client && rm -rf /var/lib/apt/lists/*
# Exporter uses rerun-sdk 0.38.1 (base); the VESPA venv must still resolve its own 0.21.0 first.
RUN python -c "import rerun; assert rerun.__version__ == '0.38.1', rerun.__version__" \
    && /opt/vespa-env/bin/python -c "import rerun; assert rerun.__version__ == '0.21.0', rerun.__version__"
WORKDIR /app
COPY embedding/clip_core.py /app/embedding/clip_core.py
COPY ai-server/ /app/ai-server/
WORKDIR /app/ai-server
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=15m --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=5)"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
