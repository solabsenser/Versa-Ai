# ===== BASE =====
FROM python:3.11-slim

# ===== WORKDIR =====
WORKDIR /app

# ===== КОПИРУЕМ ФАЙЛЫ =====
COPY . .

# ===== УСТАНОВКА =====
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir aiogram supabase python-dotenv groq

# ===== ЗАПУСК =====
CMD ["python", "bot.py"]
