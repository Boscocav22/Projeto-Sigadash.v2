# Build a partir da raiz do projeto (o banco é gerado do CSV com a mineração de python/):
#   docker build -f backend/Dockerfile -t sigadash-backend .
FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY python/ python/
COPY public/data/df_tabela_final.csv public/data/df_tabela_final.csv
COPY backend/ backend/
RUN python backend/scripts/build_database.py && rm public/data/df_tabela_final.csv

WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
