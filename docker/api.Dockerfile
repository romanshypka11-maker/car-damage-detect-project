FROM python:3.11-slim

# 1. Системні залежності (змінюються найрідше)
# Ти молодець, що додав rm -rf /var/lib/apt/lists/* — це гарна практика для зменшення ваги!
RUN apt-get update && apt-get install -y libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# 3. Інші бібліотеки проєкту
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# 4. Твій код (змінюється постійно, коли ти натискаєш Ctrl+S)
COPY . .

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]