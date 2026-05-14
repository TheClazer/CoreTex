FROM python:3.12-slim

# Install system dependencies.
# Build-arg INSTALL_TEXLIVE controls whether a full TeX Live distribution is
# installed (needed for the pdflatex compile check). Default ON for production.
# Pass `--build-arg INSTALL_TEXLIVE=0` for a fast dev build that skips ~4 GB.
ARG INSTALL_TEXLIVE=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        pandoc \
        libmagic1 \
        wget \
        curl \
    && if [ "$INSTALL_TEXLIVE" = "1" ]; then \
        apt-get install -y --no-install-recommends \
            texlive-latex-base \
            texlive-latex-recommended \
            texlive-latex-extra \
            texlive-fonts-recommended \
            texlive-publishers \
            texlive-science ; \
    fi \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements.txt first (Docker layer cache optimization)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose API port
EXPOSE 8000

# Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
