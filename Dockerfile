FROM debian:stretch

RUN useradd -m builduser -s /bin/bash

RUN apt-get update && apt-get install -qy bash python3 python3-pip python python-pip git && apt-get clean
RUN pip install -U platformio

USER builduser
RUN platformio platform install atmelavr teensy atmelsam ststm32
RUN pip3 install jinja2
WORKDIR /home/builduser/

RUN git clone https://github.com/MarlinFirmware/Marlin /home/builduser/marlin
RUN mkdir -p /home/builduser/output/
COPY marlinbuild/ /home/builduser/marlinbuild/
COPY configs/ /home/builduser/configs/

ENTRYPOINT ["/usr/bin/python3", "-m", "marlinbuild"]
