FROM ubuntu:18.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends python python-pip curl ca-certificates libnotify4 make gcc python-dev ffmpeg && \
    apt-get install -y --no-install-recommends libgtk-3-0 gstreamer-1.0 libxxf86vm1 libsm6 x11-common libsdl1.2debian

RUN mkdir /hydrus

COPY bin /hydrus/bin
COPY include /hydrus/include
COPY static /hydrus/static
COPY client.py /hydrus/client.py
COPY requirements.txt /hydrus/requirements.txt
COPY license.txt /hydrus/license.txt

WORKDIR /hydrus
RUN apt-get install -y --no-install-recommends  python-setuptools python-wheel
RUN pip install -r requirements.txt && \
    pip install https://extras.wxpython.org/wxPython4/extras/linux/gtk3/ubuntu-18.04/wxPython-4.0.4-cp27-cp27mu-linux_x86_64.whl

ENTRYPOINT ["python", "./client.py"]
