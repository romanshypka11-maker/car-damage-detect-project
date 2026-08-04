# Use the official lightweight Python image
FROM python:3.11-slim
LABEL authors="Roman Shypka"

# Install modern system dependencies required for OpenCV
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Copy only the requirements file first to maximize Docker layer caching
COPY requirements.txt .

# Install the lightweight CPU-only version of PyTorch to minimize image size
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Install the remaining dependencies from the requirements file
RUN pip install --no-cache-dir --default-timeout=1000 --retries 10 -r requirements.txt

# Copy the rest of the application source code into the container
COPY . .

# Set the default command to execute the main script
CMD ["python", "bot/mainbot.py"]