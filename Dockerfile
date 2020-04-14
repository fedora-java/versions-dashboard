FROM registry.fedoraproject.org/fedora:31

RUN : \
 && dnf -y --refresh update \
 && dnf -y install \
      python3-koji \
      python3-markdown2 \
 && :

COPY . /opt/versions-dashboard

CMD ["./opt/versions-dashboard/pkg-versions.py"]
