FROM python:3.12-slim

# Install system dependencies
# Note: texlive-full is large (~4 GB). For faster local builds during
# development, it is commented out below. Only uncomment it for production builds
# to enable full TeX Live pdflatex compile checks.
RUN apt-get update && apt-get install -y --no-install-recommends \
    pandoc \
    libmagic1 \
    wget \
    curl \
    # texlive-full \
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
