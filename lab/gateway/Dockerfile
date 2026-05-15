# Alpine 3.12 ships lighttpd 1.4.55 and dropbear 2019.78 — exact version match
FROM alpine:3.12

RUN apk add --no-cache lighttpd dropbear supervisor

# lighttpd: override server.tag so nmap HTTP header reads "lighttpd/1.4.55"
COPY lighttpd.conf /etc/lighttpd/lighttpd.conf
RUN mkdir -p /var/www/localhost/htdocs \
    && echo "<html><body><h1>gateway.local</h1></body></html>" \
       > /var/www/localhost/htdocs/index.html

# Dropbear SSH key generation
RUN mkdir -p /etc/dropbear \
    && dropbearkey -t rsa -f /etc/dropbear/dropbear_rsa_host_key 2>/dev/null \
    && dropbearkey -t ecdsa -f /etc/dropbear/dropbear_ecdsa_host_key 2>/dev/null \
    && echo 'root:toor' | chpasswd

COPY supervisord.conf /etc/supervisord.conf

EXPOSE 22 80

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisord.conf"]
