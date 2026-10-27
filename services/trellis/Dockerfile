# The devel variant includes nvcc, required to compile torchmcubes.
FROM pytorch/pytorch:2.1.2-cuda12.1-cudnn8-devel
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ENV HTTP_PROXY=${HTTP_PROXY} HTTPS_PROXY=${HTTPS_PROXY} NO_PROXY=${NO_PROXY} \
    http_proxy=${HTTP_PROXY} https_proxy=${HTTPS_PROXY} no_proxy=${NO_PROXY} \
    CUDA_HOME=/usr/local/cuda \
    TORCH_CUDA_ARCH_LIST=8.6 \
    MAX_JOBS=2 \
    CMAKE_BUILD_PARALLEL_LEVEL=2
WORKDIR /app
RUN apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=120 -o Acquire::https::Timeout=120 update \
    && apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=120 -o Acquire::https::Timeout=120 install -y --no-install-recommends \
      curl git build-essential xvfb xauth libx11-6 libegl1 libgl1 libglx0 libgles2 \
      libosmesa6 libgl1-mesa-dri \
    && rm -rf /var/lib/apt/lists/*
RUN nvcc --version
COPY requirements.txt triposr-requirements.txt ./
# Transformers 4.35/tokenizers 0.14 install the legacy Hub API. The Gradio
# Space client needs the newer Space runtime response schema, and
# huggingface-hub remains backwards compatible for TripoSR at runtime.
# torchmcubes' pyproject reads the installed torch package. Disable isolated
# builds so it can compile against the PyTorch base image.
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "scikit-build-core>=1.0" "pybind11>=2.10" ninja cmake \
    && git clone --depth 1 https://github.com/tatsy/torchmcubes.git /tmp/torchmcubes \
    && sed -i 's/set(CMAKE_CUDA_STANDARD 20)/set(CMAKE_CUDA_STANDARD 17)/; s/set(CMAKE_CXX_STANDARD 20)/set(CMAKE_CXX_STANDARD 17)/' /tmp/torchmcubes/CMakeLists.txt \
    && PIP_NO_BUILD_ISOLATION=1 pip install --no-cache-dir --no-build-isolation /tmp/torchmcubes \
    && PIP_NO_BUILD_ISOLATION=1 pip install --no-cache-dir --no-build-isolation -r triposr-requirements.txt \
    && pip install --no-cache-dir --no-deps huggingface-hub==0.36.2 \
    && pip install --no-cache-dir --no-deps gradio_client==1.14.0 \
    && python -c "import numpy, onnxruntime, rembg; assert numpy.__version__.startswith('1.'), numpy.__version__"
COPY app.py run_triposr.py workflow_6gb.json ./
RUN useradd -m -u 10001 model && mkdir -p /artifacts && chown -R model:model /app /artifacts
USER model
EXPOSE 8001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
