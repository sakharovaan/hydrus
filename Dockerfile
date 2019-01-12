FROM ubuntu:18.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends python3.6 python3-pip curl ca-certificates libnotify4 make gcc python3.6-dev ffmpeg && \
    apt-get install -y --no-install-recommends libgtk-3-0 gstreamer-1.0 libxxf86vm1 libsm6 x11-common libsdl1.2debian

RUN mkdir /hydrus
WORKDIR /hydrus
COPY requirements.txt /hydrus/requirements.txt

RUN apt-get install -y --no-install-recommends python3-setuptools python3-wheel
RUN pip3 install -r requirements.txt && \
    pip3 install https://extras.wxpython.org/wxPython4/extras/linux/gtk3/ubuntu-18.04/wxPython-4.0.4-cp36-cp36m-linux_x86_64.whl

RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev && \
    pip3 install psycopg2

ARG RUN_ENV
COPY requirements_test.txt /hydrus/requirements_test.txt
RUN if [ "x$RUN_ENV" = "xtest" ]; then pip3 install -r requirements_test.txt; fi

RUN apt-get update && apt-get install locales && locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

COPY bin /hydrus/bin
COPY include /hydrus/include
COPY static /hydrus/static
COPY client.py /hydrus/client.py
COPY test.py /hydrus/test.py
COPY server.py /hydrus/server.py
COPY license.txt /hydrus/license.txt

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
RUN chmod +x /hydrus/client.py

ENTRYPOINT ["/entrypoint.sh"]
