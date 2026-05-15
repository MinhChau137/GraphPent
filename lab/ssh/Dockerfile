FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y openssh-server && rm -rf /var/lib/apt/lists/*

RUN mkdir /var/run/sshd \
    && echo 'root:toor' | chpasswd \
    && sed -i \
       -e 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' \
       -e 's/PermitRootLogin prohibit-password/PermitRootLogin yes/' \
       /etc/ssh/sshd_config \
    && ssh-keygen -A

EXPOSE 22

CMD ["/usr/sbin/sshd", "-D"]
