FROM python:3.9-slim


RUN apt-get update && apt-get install -y curl

WORKDIR /app
COPY fastapi_cluster_server.py /app/
RUN pip install fastapi uvicorn pyraft pydantic protobuf pyraft
RUN pip install requests

CMD ["python", "fastapi_cluster_server.py"]
