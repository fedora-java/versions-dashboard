FROM registry.fedoraproject.org/fedora:31

RUN : \
 && dnf -y --refresh update \
 && dnf -y install \
      python3-koji \
      python3-markdown2 \
 && dnf -y clean all \
 && adduser versions-dashboard \
 && :

COPY . /opt/versions-dashboard

USER versions-dashboard
ENTRYPOINT ["/opt/versions-dashboard/pkg-versions.py"]
