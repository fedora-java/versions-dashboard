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

import aiohttp
import asyncio
import json
import koji
import markdown2
import os
import re
import sys
import time

from aiohttp.client_exceptions import ServerDisconnectedError
from concurrent.futures import ThreadPoolExecutor

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
	"google-guice": "guice",
	"httpcomponents-project": "httpcomponents-parent-pom",
	"jakarta-annotations": "common-annotations-api",
	"jakarta-servlet": "servlet-api",
	"java_cup": "cup",
	"junit": "junit4",
	"maven-parent": "maven-parent-pom",
	"maven-plugin-build-helper": "build-helper-maven-plugin",
	"maven-plugin-bundle": "maven-bundle-plugin",
	"mojo-parent": "mojo-parent-pom",
	"objectweb-asm": "asm",
	"osgi-compendium": "osgi-cmpn",
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

def get_packages() -> {str}:
	ks = koji.ClientSession("https://koji.kjnet.xyz/kojihub")
	return set([package["package_name"] for package in filter(
		lambda package: not package["blocked"], ks.listPackages("mbi-f32", inherited = True)
	)])

def get_koji_versions(package_names: [str], url: str, tag: str) -> {str : str}:
	ks = koji.ClientSession(url)
	ks.multicall = True
	for pkg in package_names:
		ks.listTagged(tag, package = pkg, latest = True, inherit = True)
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
	return get_koji_versions(package_names, "https://koji.kjnet.xyz/kojihub", "mbi-f32")

async def get_async_data(packages, version_columns):
	async def get_upstream_version(package_name: str) -> {str: str}:
		result = dict()
		request_retries = 5
		
		while request_retries > 0:
			try:
				async with session.get(f"https://release-monitoring.org/api/v2/packages/?name={package_name}&distribution=Fedora") as package_response:
					if not package_response:
						raise RuntimeError(f"Upstream package {package_name} not found, number of retries: {retries}")
					
					project_items = (await package_response.json())["items"]
					
					if len(project_items) == 0:
						raise RuntimeError(f"Upstream package {package_name} not found, there is no package under such name")
					
					project_name = project_items[0]["project"]
				break
			except ServerDisconnectedError:
				request_retries -= 1
				continue
		
		while request_retries > 0:
			try:
				async with session.get(f"https://release-monitoring.org/api/v2/projects/?name={project_name}") as project_response:
					if not project_response:
						raise RuntimeError(f"Upstream project {project_name} not found, number of retries: {retries}")
					
					versions = (await project_response.json())["items"][0]["versions"]
					
					result["latest"] = normalize_version(versions[0])
					
					# The first version not having a tilde in its normalized string
					try:
						result["latest-stable"] = normalize_version(
							next((v for v in versions if not "~" in normalize_version(v)))
						)
					except StopIteration:
						pass
				break
			except ServerDisconnectedError:
				request_retries -= 1
				continue
		
		return result
	
	async def get_upstream_versions(packages):
		versions = await asyncio.gather(*[get_upstream_version(p) for p in packages])
		return {p: v for p, v in zip(packages, versions)}
	
	async def get_upstream_versions_cached(package_names: [str]) -> {str: {str: str}}:
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
	
	async def get_mbi_bootstrap_versions() -> {str: str}:
		package_names = None
		
		async def get_mbi_bootstrap_version(name: str) -> str:
			async with session.get(f"https://raw.githubusercontent.com/fedora-java/javapackages-bootstrap/master/project/{name}.properties") as response:
				content = (await response.content.read()).decode()
				result = next(re.finditer(r"^version=(.*)$", content, re.MULTILINE)).group(1)
				return result
			
		async with session.get("https://github.com/fedora-java/javapackages-bootstrap/tree/master/project") as response:
			content = (await response.content.read()).decode()
			pattern = r"\"/fedora-java/javapackages-bootstrap/blob/master/project/(.*?)(:?\.xml|\.properties)\""
			package_names = {name.group(1) for name in re.finditer(pattern, content)}
		
		package_names.remove("mbi")
		
		versions = await asyncio.gather(*[get_mbi_bootstrap_version(p) for p in package_names])
		return {p: v for p, v in zip(package_names, versions)}
	
	async def get_comments() -> {str : {str: str}}:
		request_retries = 5
		
		while request_retries > 0:
			try:
				async with session.get("https://pagure.io/java-pkg-versions-comments/raw/master/f/comments.md") as response:
					if response.status != 200:
						raise Exception("Could not obtain comments")
					
					result = dict()
					name = str()
					comment = None
					
					while not response.content.at_eof():
						line = (await response.content.readline()).decode()
						
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
				break
			except ServerDisconnectedError:
				request_retries -= 1
				continue
		
		return result
	
	async with aiohttp.ClientSession() as session:
		with ThreadPoolExecutor(max_workers = 16) as executor:
			futures = []
			
			for release in version_columns["fedora"]:
				futures.append(executor.submit(get_fedora_versions, packages, release))
			
			futures.append(executor.submit(get_mbi_versions, packages))
			
			####################################################################
			
			jp_bp, upstream, comments = await asyncio.gather(*[
				get_mbi_bootstrap_versions(),
				get_upstream_versions_cached(packages),
				get_comments(),
			])
			
			fedoras = {version_columns["fedora"][i]: futures[i].result()
				for i in range(len(version_columns["fedora"]))
			}
			
			mbi = futures[len(version_columns["fedora"])].result()
			
			####################################################################
			
			result = {package: {
				"fedora": {release: fedoras[release][package]
					for release in  fedoras.keys()
				},
				"mbi": {
					version_columns["mbi"][0]: jp_bp.get(bootstrap_package_name.get(package, package), ""),
					version_columns["mbi"][1]: mbi[package],
				},
				"upstream": upstream[package],
				"comments": {},
			} for package in sorted(packages)}
			
			for k, v in comments.items():
				try:
					result[k]["comments"] = v
				except KeyError:
					print(f"Warning: package \"{package}\" has comments on the page but is not present in Koji")
			
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

################################################################################
# Main function

packages = get_packages()
fedora_releases = range(28, 34 + 1)

version_columns = {
	"fedora": [f"f{i}" for i in fedora_releases],
	"mbi": ["jp-bootstrap", "mbi"],
}

versions_result = asyncio.run(get_async_data(packages, version_columns))

with open(output_path, "w") as output_file:
	result = {
		"time-generated": time.ctime(),
		"hostname": os.environ.get("HOSTNAME", "local"),
		"version-columns": version_columns,
		"upstream-columns": ["latest", "latest-stable"],
		"versions": versions_result,
	}
	json.dump(result, output_file, indent = 2)
	output_file.write("\n")
