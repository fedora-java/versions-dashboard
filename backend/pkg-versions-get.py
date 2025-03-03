#!/usr/bin/env python3
#
# Copyright (c) 2021 Red Hat, Inc.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# Author: Marian Koncek <mkoncek@redhat.com>

import time
import json
import koji
import os
import sys
import requests
import time
import xml.etree.ElementTree as xmltree

from concurrent.futures import ThreadPoolExecutor as thread_pool

from normalize_version import normalize

def log_debug(message):
    print("[DEBUG] " + message, file = sys.stderr)

def log_info(message):
    print("[INFO] " + message, file = sys.stderr)

def log_warn(message):
    print("[WARN] " + message, file = sys.stderr)

# The mapping from package name to package name used in javapackages-bootstrap repository
bootstrap_package_name = {
    "apache-commons-beanutils": "commons-beanutils",
    "apache-commons-cli": "commons-cli",
    "apache-commons-codec": "commons-codec",
    "apache-commons-collections": "commons-collections",
    "apache-commons-compress": "commons-compress",
    "apache-commons-io": "commons-io",
    "apache-commons-jxpath": "commons-jxpath",
    "apache-commons-lang3": "commons-lang",
    "apache-commons-logging": "commons-logging",
    "apache-commons-parent": "commons-parent-pom",
    "apache-parent": "apache-pom",
    "aqute-bnd": "bnd",
    "beust-jcommander": "jcommander",
    "felix-parent": "felix-parent-pom",
    "google-gson": "gson",
    "google-guice": "guice",
    "httpcomponents-project": "httpcomponents-parent-pom",
    "jakarta-activation1": "jaf-api",
    "jakarta-annotations": "common-annotations-api",
    "jakarta-cdi": "cdi",
    "jakarta-inject": "injection-api",
    "jakarta-mail": "mail-api",
    "jakarta-servlet": "servlet-api",
    "java_cup": "cup",
    "junit": "junit4",
    "maven-parent": "maven-parent-pom",
    "mojo-parent": "mojo-parent-pom",
    "objectweb-asm": "asm",
    "osgi-compendium": "osgi-cmpn",
    "velocity": "velocity-engine",
    "woodstox-core": "woodstox",
}

################################################################################

def retry_response(request, retries, timeout = 0, **kwargs):
    response = None
    while retries > 0:
        response = requests.get(request, kwargs)
        time.sleep(timeout)
        if response.status_code == 200:
            break
        retries -= 1
    return response

def get_upstream_version(package_name: str) -> {str: str}:
    log_info(f"obtaining upstream version information for package {package_name}")
    result = {}
    retries = 3
    package_response = retry_response(
        f"https://release-monitoring.org/api/v2/packages/?name={package_name}&distribution=Fedora",
        retries,
        timeout = 2,
    )
    
    if not package_response:
        raise RuntimeError(f"Upstream package {package_name} not found, number of retries: {retries}")
    
    project_items = package_response.json()["items"]
    if len(project_items) == 0:
        raise RuntimeError(f"Upstream package {package_name} not found, there is no package under such name")
    
    project_name = project_items[0]["project"]
    project_response = retry_response(
        f"https://release-monitoring.org/api/v2/projects/?name={project_name}",
        retries,
        timeout = 2,
    )
    
    if not project_response:
        raise RuntimeError(f"Upstream project {project_name} not found, number of retries: {retries}")
    
    versions = project_response.json()["items"][0]["versions"]
    result["latest"] = normalize(versions[0])
    
    # The first version not having a tilde in its normalized string
    try:
        result["latest-stable"] = normalize(
            next((v for v in versions if not "~" in normalize(v)))
        )
    except StopIteration:
        pass
    
    return result

def get_koji_versions(package_names: [str], url: str, tag: str) -> {str : str}:
    ks = koji.ClientSession(url)
    ks.multicall = True
    for pkg in package_names:
        ks.listTagged(tag, package = pkg, latest = True)
    result = dict()
    for [builds] in ks.multiCall(strict = True):
        if builds:
            result[builds[0]["package_name"]] = builds[0]["version"]
    for package_name in package_names:
        if package_name not in result.keys():
            result[package_name] = str()
    return result

def get_fedora_versions(package_names: [str], release: str) -> {str: str}:
    log_info("obtaining fedora version information...")
    return get_koji_versions(package_names, "https://koji.fedoraproject.org/kojihub", release)

def get_bootstrap_version(package_name: str) -> str:
    log_info(f"obtaining bootstrap version information for package {package_name}")
    result = ""
    req = requests.get(f"https://raw.githubusercontent.com/fedora-java/javapackages-bootstrap/master/project/{package_name}.properties")
    if not req.ok:
        log_warn(f"package {package_name} not found in upstream javapackages-bootstrap GitHub repository")
    else:
        result = req.text
        begin = result.find("version=")
        result = result[begin + len("version="):]
        result = result[:result.find("\n")]
    return result

################################################################################

log_debug("backend started...")

request_pool = thread_pool(1)

output_path = os.environ.get("OUT_JSON", "versions.json")

futures = {
    "fedora": {"f" + str(v): None for v in range(40, 42 + 1)},
    "upstream": {},
    "jp-bootstrap": {}
}

groups = retry_response(os.environ["URL_PACKAGE_GROUPS"], 3).json()["groups"]
log_debug("package groups obtained")

result = {pkg: {} for group in groups.values() for pkg in group}

# Futures

for version in futures["fedora"].keys():
    futures["fedora"][version] = request_pool.submit(get_fedora_versions, result.keys(), version)

for pkg in result.keys():
    futures["upstream"][pkg] = request_pool.submit(get_upstream_version, pkg)
    futures["jp-bootstrap"][pkg] = request_pool.submit(get_bootstrap_version, bootstrap_package_name.get(pkg, pkg))

# Result

for fedora_version in futures["fedora"].keys():
    for pkg, version in futures["fedora"][fedora_version].result().items():
        result[pkg].setdefault("fedora", {})[fedora_version] = version
log_debug("fedora versions obtained")

for pkg in result.keys():
    result[pkg]["upstream"] = futures["upstream"][pkg].result()
    log_debug("upstream versions obtained")
    result[pkg]["jp-bootstrap"] = futures["jp-bootstrap"][pkg].result()
    log_debug("bootstrap versions obtained")

with open(output_path, "w") as output_file:
    log_debug(f"output file {output_path} created")
    result = {
        "time-generated": time.ctime(),
        "hostname": os.environ.get("HOSTNAME", "local"),
        "version-columns": {
            "fedora": [f for f in futures["fedora"].keys()],
        },
        "upstream-columns": ["latest", "latest-stable"],
        "versions": result,
        "groups": groups,
    }
    json.dump(result, output_file, indent = 2)
    output_file.write("\n")

log_debug("backend finished")
