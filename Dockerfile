# AWS CostLens - Docker Image
FROM python:3.11-slim

LABEL maintainer="Ernesto Calzadilla Martínez"
LABEL description="AWS CostLens - Cost Intelligence Tool"

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY aws_costlens/ ./aws_costlens/
COPY pyproject.toml .
COPY README.md .

# Install package
RUN pip install --no-cache-dir .

# Set entrypoint
ENTRYPOINT ["aws-costlens"]
CMD ["--help"]
