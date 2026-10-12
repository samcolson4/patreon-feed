FROM python:3.13-alpine
WORKDIR /app
COPY app.py .
ENV DATA_DIR=/data PORT=8000 PYTHONUNBUFFERED=1
RUN mkdir /data && chown nobody /data
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=1m CMD wget -qO- http://127.0.0.1:8000/healthz || exit 1
USER nobody
CMD ["python", "app.py"]
