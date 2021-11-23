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
ENTRYPOINT ["/usr/bin/sh", "-c", "cd /opt/versions-dashboard && URL_PACKAGE_NAMES='https://mbi-artifacts.s3.eu-central-1.amazonaws.com/3406f152-0ceb-4291-8f27-6db7db011c16/subject.xml' ./pkg-versions-get.py"]
