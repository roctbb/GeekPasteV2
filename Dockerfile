# Используем официальный образ Python
FROM python:3.11

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы проекта в контейнер
COPY . .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем переменные окружения
ENV FLASK_APP=paste_server.py
ENV FLASK_RUN_HOST=0.0.0.0

# Открываем порт
EXPOSE 8084

# Запускаем приложение
CMD ["flask", "run"]