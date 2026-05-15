# Ubuntu 20.04: Exim 4.93 (≈4.92), Dovecot 2.3.7.2 (exact match)
FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    openssh-server \
    exim4 \
    exim4-daemon-light \
    dovecot-imapd \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Configure Exim4 for standalone/internet mode, listen on all interfaces
RUN printf '%s\n' \
    "dc_eximconfig_configtype='internet'" \
    "dc_other_hostnames='mailserver.local'" \
    "dc_local_interfaces='0.0.0.0 ; ::1'" \
    "dc_readhost=''" \
    "dc_relay_domains=''" \
    "dc_minimaldns='false'" \
    "dc_relay_nets=''" \
    "dc_smarthost=''" \
    "dc_use_split_config='false'" \
    "dc_hide_mailname=''" \
    "dc_mailname_in_oh='true'" \
    "dc_localdelivery='mail_spool'" \
    > /etc/exim4/update-exim4.conf.conf \
    && update-exim4.conf

# Dovecot: enable plaintext auth, IMAP
RUN sed -i \
    -e 's/#protocols = imap pop3 lmtp submission/protocols = imap/' \
    /etc/dovecot/dovecot.conf \
    && sed -i \
       -e 's/#disable_plaintext_auth = yes/disable_plaintext_auth = no/' \
       -e 's/auth_mechanisms = plain/auth_mechanisms = plain login/' \
       /etc/dovecot/conf.d/10-auth.conf \
    && sed -i \
       -e 's|#mail_location =.*|mail_location = mbox:~/mail:INBOX=/var/mail/%u|' \
       /etc/dovecot/conf.d/10-mail.conf

# SSH
RUN mkdir -p /var/run/sshd \
    && echo 'root:toor' | chpasswd \
    && sed -i \
       -e 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' \
       -e 's/PermitRootLogin prohibit-password/PermitRootLogin yes/' \
       /etc/ssh/sshd_config \
    && ssh-keygen -A

COPY supervisord.conf /etc/supervisor/conf.d/lab.conf

EXPOSE 22 25 143

CMD ["/usr/bin/supervisord", "-n"]
