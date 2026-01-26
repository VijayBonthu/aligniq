FROM python:3.14.0a4-alpine3.21

WORKDIR /app/backend

COPY requirements.txt .
RUN pip install --nocache-dir -r requirements.txt

COPY . /app/backend/

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host" "0.0.0.0", "--port", "8080"]