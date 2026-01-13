ARG BUILD_FROM
FROM $BUILD_FROM

# Cache-buster: change this value to force rebuild
ARG CACHEBUST=1
RUN echo "Build cache-bust: ${CACHEBUST}"

RUN apk add --no-cache python3 py3-pip

WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt

COPY app /app
RUN python3 -m compileall /app
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
