#!/usr/bin/env python3
#
# Copyright (c) 2020 Red Hat, Inc.
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

import json
import koji
import markdown2
import os
import re
import requests
import sys
import time

from concurrent.futures import ThreadPoolExecutor as thread_pool

################################################################################

# The mapping from package name to package name used in mbi-bootstrap repository
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
	"atinject": "injection-api",
	"beust-jcommander": "jcommander",
	"cdi-api": "cdi",
	"felix-parent": "felix-parent-pom",
	"glassfish-annotation-api": "common-annotations-api",
	"glassfish-servlet-api": "servlet-api",
	"google-guice": "guice",
	"httpcomponents-project": "httpcomponents-parent-pom",
	"java_cup": "cup",
	"junit": "junit4",
	"maven-parent": "maven-parent-pom",
	"maven-plugin-build-helper": "build-helper-maven-plugin",
	"maven-plugin-bundle": "maven-bundle-plugin",
	"mojo-parent": "mojo-parent-pom",
	"objectweb-asm": "asm",
	"osgi-annotation": "osgi",
	"osgi-compendium": "osgi",
	"osgi-core": "osgi",
	"plexus-build-api": "sisu-build-api",
	"sisu": "sisu-inject",
	"sonatype-oss-parent": "oss-parent-pom",
	"velocity": "velocity-engine",
}

def normalize_version(version: str) -> str:
	version_name = version[:]
	version_name = version_name.replace("_", ".")
	version_name = version_name.replace("-", ".")
	
	# Match classical version symbols (numbers and dot)
	match = re.match("([.0-9]*[0-9]+)(.*)", version_name)
	
	if not match:
		raise Exception("Invalid version name: " + version_name)
	
	leading = match.group(1)
	trailing = match.group(2)
	
	if trailing == ".Final":
		return leading
	
	# If the proper version is followed by a single letter, keep it
	# Use tilde split otherwise
	if not re.match("^[a-zA-Z]$", trailing):
		if trailing:
			if trailing.startswith((".", "~")):
				trailing = trailing[1:]
			
			# Service pack post-release should not use pre-release tilde
			if trailing.startswith("SP"):
				trailing = "." + trailing
			
			else:
				trailing = "~" + trailing
		
		trailing = trailing.replace("-", ".")
	
	return leading + trailing

def retry_response(request, retries, **kwargs):
	response = None
	
	while retries > 0:
		response = requests.get(request, kwargs)
		
		if response.status_code == 200:
			break
		
		retries -= 1
	
	return response

def get_packages() -> {str}:
	ks = koji.ClientSession("https://koji.kjnet.xyz/kojihub")
	return set([package["package_name"] for package in filter(
		lambda package: not package["blocked"], ks.listPackages("jp")
	)])

def get_upstream_version(package_name: str) -> {str: str}:
	result = dict()
	
	retries = 3
	package_response = retry_response(
		f"https://release-monitoring.org/api/v2/packages/?name={package_name}&distribution=Fedora",
		retries,
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
	)
	
	if not project_response:
		raise RuntimeError(f"Upstream project {project_name} not found, number of retries: {retries}")
	
	versions = project_response.json()["items"][0]["versions"]
	
	result["latest"] = normalize_version(versions[0])
	
	# The first version not having a tilde in its normalized string
	try:
		result["latest-stable"] = normalize_version(
			next((v for v in versions if not "~" in normalize_version(v)))
		)
	except StopIteration:
		pass
	
	return result

def get_upstream_versions(package_names: [str]) -> {str: {str: str}}:
	result = dict()
	
	futures = list()
	
	for package_name in package_names:
		futures.append(request_pool.submit(get_upstream_version, package_name))
	
	for package_name, project_version in zip(package_names, futures):
		result[package_name] = project_version.result()
	
	return result

def get_upstream_versions_cached(package_names: [str]) -> {str: (str, str)}:
	update_cache = False
	result = {}
	time_retrieved_literal = "time-retrieved"
	
	if not os.path.exists(upstream_cache_path):
		update_cache = True
		
	else:
		with open(upstream_cache_path, "r") as cache_file:
			cache = json.load(cache_file)
		
		if time.time() - cache[time_retrieved_literal] > upstream_cache_interval:
			update_cache = True
		
		else:
			result = cache["packages"]
	
	if update_cache:
		result = get_upstream_versions(package_names)
		
		with open(upstream_cache_path, "w") as cache_file:
			result = {time_retrieved_literal: time.time(), "packages": result}
			json.dump(result, cache_file, indent = 2)
			cache_file.write("\n")
	
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
	return get_koji_versions(package_names, "https://koji.fedoraproject.org/kojihub", release)

def get_mbi_versions(package_names: [str]) -> {str: str}:
	return get_koji_versions(package_names, "https://koji.kjnet.xyz/kojihub", "jp")

def get_mbi_bootstrap_packages() -> {str}:
	result = set()
	
	index = 0
	response = retry_response("https://pagure.io/mbi/stage2/blob/master/f/project", 3)
	content = response.content.decode("utf-8")
	pattern = "\"/mbi/stage2/blob/master/f/project/"

	while True:
		index = content.find(pattern, index)
		
		if index == -1:
			break
		
		index += len(pattern)
		
		end = content.find(".xml\"", index)
		result.add(content[index : end])
	
	return result

def get_mbi_bootstrap_versions(package_names: {str}) -> {str: str}:
	result = dict()
	
	futures = list()
	
	def get_mbi_bootstrap_version(name: str) -> str:
		request = retry_response(f"https://pagure.io/mbi/stage2/raw/master/f/project/{name}.xml", 3)
		content = request.content.decode("utf-8")
		
		version_str = "<version>"
		version_str_end = "</version>"
		
		begin = content.find(version_str) + len(version_str)
		end = content.find(version_str_end, begin)
		
		return content[begin : end]
	
	for package_name in package_names:
		futures.append(request_pool.submit(get_mbi_bootstrap_version, bootstrap_package_name.get(package_name, package_name)))
	
	for package_name, project_version in zip(package_names, futures):
		result[package_name] = project_version.result()
	
	return result

def get_comments() -> {str : {str: str}}:
	response = retry_response(
		"https://pagure.io/java-pkg-versions-comments/raw/master/f/comments.md",
		3,
		timeout = 7)
	
	if response.status_code != 200:
		raise Exception("Could not obtain comments")
	
	result = dict()
	name = str()
	comment = str()

	for line in response.text.splitlines():
		# A new package name
		if line.startswith("#") and not line.startswith("##"):
			name = line[1:].strip()
			result[name] = dict()
		
		# A new tag
		elif line.startswith("##"):
			if name:
				match = re.match("##\\s*(.*?)\\s*:\\s*(.*)", line)
				result[name][match.group(1)] = match.group(2).rstrip()
		
		# End of the comment for the current package name
		elif line.startswith("---") or (line.startswith("#") and not line.startswith("##") and name):
			if name:
				match = re.match("<p>(.*)</p>\\s*", markdown2.markdown(comment), re.DOTALL)
				result[name]["comment"] = match.group(1)
			name = str()
			comment = str()
		
		elif name:
			comment += line
			comment += "\n"
	
	return result

################################################################################
# Shared variables

output_path = os.environ.get("OUT_JSON", "versions.json")

# If the cache file is older than this time (in seconds), regenerate it
upstream_cache_interval = 1 * 60 * 60
upstream_cache_path = os.environ.get("CACHE_FILE", "/tmp/pkg-versions-upstream-cache.json")

request_pool = thread_pool(40)

################################################################################
# Main function

result = {pkg: {} for pkg in get_packages()}
futures = list()
column_names = list()

for fedora_version in [f"f{i}" for i in range(28, 34)]:
	futures.append(request_pool.submit(get_fedora_versions, result.keys(), fedora_version))
	column_names.append(fedora_version)

mbi_bootstrap = get_mbi_bootstrap_packages()
futures.append(request_pool.submit(get_mbi_bootstrap_versions,
	{name for name in result.keys() if bootstrap_package_name.get(name, name) in mbi_bootstrap}))
column_names.append("mbi-bootstrap")

futures.append(request_pool.submit(get_mbi_versions, result.keys()))
column_names.append("mbi")

futures.append(request_pool.submit(get_upstream_versions_cached, result.keys()))
column_names.append("upstream")

futures.append(request_pool.submit(get_comments))
column_names.append("comments")

for i in range(len(column_names)):
	inner = futures[i].result()
	for pkg, dic in result.items():
		dic[column_names[i]] = inner.get(pkg)

with open(output_path, "w") as output_file:
	result = {
		"time-generated": time.ctime(),
		"host": os.environ.get("HOSTNAME", "local"),
		"version-columns": column_names[:-1],
		"versions": result,
	}
	json.dump(result, output_file, indent = 2)
	output_file.write("\n")
