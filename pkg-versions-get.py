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

def get_upstream_versions_cached(package_names: [str]) -> {str: {str: str}}:
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
			json.dump({
				time_retrieved_literal: time.time(),
				"packages": result
			}, cache_file, indent = 2)
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
	comment = None

	for line in response.text.splitlines():
		# A new package name
		if line.startswith("#") and not line.startswith("##"):
			name = line[1:].strip()
			result[name] = dict()
			comment = str()
		
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
			comment = None
		
		elif name:
			comment += line
			comment += "\n"
	
	return result

################################################################################
# Tests

assert(normalize_version("1.0b3") == "1.0~b3")
assert(normalize_version("2.5.0-rc1") == "2.5.0~rc1")
assert(normalize_version("2.0b6") == "2.0~b6")
assert(normalize_version("2.0.SP1") == "2.0.SP1")
assert(normalize_version("3_2_12") == "3.2.12")
assert(normalize_version("1.0-20050927.133100") == "1.0.20050927.133100")
assert(normalize_version("3.0.1-b11") == "3.0.1~b11")
assert(normalize_version("5.0.1-b04") == "5.0.1~b04")
assert(normalize_version("0.11b") == "0.11b")
assert(normalize_version("1_6_2") == "1.6.2")
assert(normalize_version("1.0.1.Final") == "1.0.1")
assert(normalize_version("3.0.0.M1") == "3.0.0~M1")
assert(normalize_version("6.0-alpha-2") == "6.0~alpha.2")
assert(normalize_version("4.13-beta-1") == "4.13~beta.1")
assert(normalize_version("5.5.0-M1") == "5.5.0~M1")
assert(normalize_version("3.0.0-M2") == "3.0.0~M2")
assert(normalize_version("3.0.0-M1") == "3.0.0~M1")
assert(normalize_version("3.0.0-M3") == "3.0.0~M3")
assert(normalize_version("3.0.0-beta.1") == "3.0.0~beta.1")
assert(normalize_version("1.0-alpha-2.1") == "1.0~alpha.2.1")
assert(normalize_version("1.0-alpha-8") == "1.0~alpha.8")
assert(normalize_version("1.0-alpha-18") == "1.0~alpha.18")
assert(normalize_version("1.0-alpha-10") == "1.0~alpha.10")
assert(normalize_version("1.0-beta-7") == "1.0~beta.7")
assert(normalize_version("1.0-alpha-5") == "1.0~alpha.5")
assert(normalize_version("2.0-M10") == "2.0~M10")
assert(normalize_version("7.0.0-beta4") == "7.0.0~beta4")

################################################################################
# Shared variables

output_path = os.environ.get("OUT_JSON", "versions.json")

# If the cache file is older than this time (in seconds), regenerate it
upstream_cache_interval = 1 * 60 * 60
upstream_cache_path = os.environ.get("CACHE_FILE", "/tmp/pkg-versions-upstream-cache.json")

request_pool = thread_pool(20)

################################################################################
# Main function

result = {pkg: {} for pkg in get_packages()}
futures = dict()

version_columns = {
	"fedora": [f"f{i}" for i in range(28, 35)],
	"mbi": ["mbi-bootstrap", "mbi"],
}

futures["fedora"] = dict()
for fedora_version in version_columns["fedora"]:
	futures["fedora"][fedora_version] = request_pool.submit(get_fedora_versions, result.keys(), fedora_version)

futures["mbi"] = dict()
mbi_bootstrap = get_mbi_bootstrap_packages()
futures["mbi"]["mbi-bootstrap"] = request_pool.submit(get_mbi_bootstrap_versions,
	{name for name in result.keys() if bootstrap_package_name.get(name, name) in mbi_bootstrap})

futures["mbi"]["mbi"] = request_pool.submit(get_mbi_versions, result.keys())
futures["upstream"] = request_pool.submit(get_upstream_versions_cached, result.keys())
futures["comments"] = request_pool.submit(get_comments)

for column_name in version_columns.keys():
	for k, dic in result.items():
		dic[column_name] = dict()
	
	for column_version, versions_future in futures[column_name].items():
		versions = versions_future.result()
		for package, version in versions.items():
			result[package][column_name][column_version] = version

for package, upstream_versions in futures["upstream"].result().items():
	result[package]["upstream"] = upstream_versions

for package, comments in futures["comments"].result().items():
	try:
		result[package]["comments"] = comments
	except KeyError:
		print(f"Package {package} has comments on the page but is not present in Koji")

with open(output_path, "w") as output_file:
	result = {
		"time-generated": time.ctime(),
		"hostname": os.environ.get("HOSTNAME", "local"),
		"version-columns": {
			"fedora": [f for f in futures["fedora"]],
			"mbi": [m for m in futures["mbi"]],
		},
		"upstream-columns": ["latest", "latest-stable"],
		"versions": result,
	}
	json.dump(result, output_file, indent = 2)
	output_file.write("\n")
