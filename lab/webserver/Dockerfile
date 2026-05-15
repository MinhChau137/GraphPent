# Apache httpd 2.4.49 — exact version from official image
# Enables mod_ssl + mod_cgid for CVE-2021-41773 demo
FROM httpd:2.4.49

ENV DEBIAN_FRONTEND=noninteractive

# httpd:2.4.49 is Debian Buster (EOL) — redirect apt to archive mirror
RUN sed -i \
    -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' \
    -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' \
    -e '/buster-updates/d' \
    /etc/apt/sources.list

# Install openssl for self-signed cert
RUN apt-get update && apt-get install -y openssl && rm -rf /var/lib/apt/lists/*

# Enable SSL, socache, and CGI modules
RUN sed -i \
    -e 's/^#\(LoadModule ssl_module\)/\1/' \
    -e 's/^#\(LoadModule socache_shmcb_module\)/\1/' \
    -e 's/^#\(LoadModule cgid_module\)/\1/' \
    -e 's/^#\(Include conf\/extra\/httpd-ssl.conf\)/\1/' \
    /usr/local/apache2/conf/httpd.conf

# Expose full version in Server header (nmap reads this)
RUN echo "ServerTokens Full" >> /usr/local/apache2/conf/httpd.conf \
    && echo "ServerSignature On" >> /usr/local/apache2/conf/httpd.conf

# Generate self-signed cert for HTTPS
RUN openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout /usr/local/apache2/conf/server.key \
    -out /usr/local/apache2/conf/server.crt \
    -subj "/C=VN/ST=HN/L=Hanoi/O=Lab/CN=webserver.local"

# CGI scripts dir for CVE-2021-41773
RUN mkdir -p /usr/local/apache2/cgi-bin \
    && echo '#!/bin/bash\necho "Content-Type: text/plain"\necho ""\necho "CGI works"' \
       > /usr/local/apache2/cgi-bin/test.sh \
    && chmod +x /usr/local/apache2/cgi-bin/test.sh

# Simple index page
RUN echo "<html><body><h1>webserver.local - Apache 2.4.49</h1></body></html>" \
    > /usr/local/apache2/htdocs/index.html

EXPOSE 80 443
