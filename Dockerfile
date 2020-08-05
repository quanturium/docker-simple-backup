FROM python:3.7-alpine
COPY requirements.txt /tmp/
RUN pip install -r /tmp/requirements.txt
COPY docker_simple_backup/ /root
WORKDIR /root
ENTRYPOINT [ "python3", "-u", "./run.py" ]