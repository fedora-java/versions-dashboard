FROM registry.fedoraproject.org/fedora:33

RUN : \
 && dnf -y --refresh update \
 && dnf -y install \
      python3-koji \
 && dnf -y clean all \
 && adduser versions-dashboard \
 && :

COPY . /opt/versions-dashboard

USER versions-dashboard
ENTRYPOINT ["/usr/bin/sh", "-c", "cd /opt/versions-dashboard && ./pkg-versions-get.py"]
