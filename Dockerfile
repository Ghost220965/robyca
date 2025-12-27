FROM python:3.9-slim

WORKDIR /app



# Instalăm modulele tale specifice

RUN pip install flask flask-sqlalchemy requests



# Copiem fișierele tale (inclusiv flask_app.py)

COPY . .



# Expunem portul pentru Flask

EXPOSE 5000



# Comanda de pornire

CMD ["python3", "flask_app.py"]