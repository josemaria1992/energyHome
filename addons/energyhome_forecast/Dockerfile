ARG BUILD_FROM
FROM $BUILD_FROM

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apk add --no-cache python3 py3-pip py3-virtualenv

COPY app/requirements.txt /app/requirements.txt

RUN python3 -m venv /opt/venv \
  && /opt/venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel \
  && /opt/venv/bin/pip install --no-cache-dir -r /app/requirements.txt

COPY app /app
COPY run.sh /run.sh
RUN chmod a+x /run.sh

RUN /opt/venv/bin/python -m compileall /app

CMD ["/run.sh"]
