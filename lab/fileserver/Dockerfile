FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    openssh-server \
    proftpd-basic \
    samba \
    samba-common-bin \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# ProFTPD: override banner to report version 1.3.5
# ServerIdent replaces the 220 greeting — nmap regex matches "ProFTPD (\d+\.[\d.]+)"
COPY proftpd.conf /etc/proftpd/proftpd.conf

# Samba share
COPY smb.conf /etc/samba/smb.conf
RUN mkdir -p /srv/share && chmod 777 /srv/share

# SSH: allow root login
RUN mkdir -p /var/run/sshd \
    && echo 'root:toor' | chpasswd \
    && sed -i \
       -e 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' \
       -e 's/PermitRootLogin prohibit-password/PermitRootLogin yes/' \
       /etc/ssh/sshd_config \
    && ssh-keygen -A

# FTP user
RUN useradd -m -s /bin/bash ftpuser \
    && echo "ftpuser:ftppass" | chpasswd \
    && printf "ftppass\nftppass\n" | smbpasswd -a ftpuser -s 2>/dev/null || true

COPY supervisord.conf /etc/supervisor/conf.d/lab.conf

EXPOSE 21 22 139 445

CMD ["/usr/bin/supervisord", "-n"]
