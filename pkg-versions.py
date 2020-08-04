#!/usr/bin/python3
#
# Copyright (c) 2019-2020 Red Hat, Inc.
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
import rpm
import time

from concurrent.futures import ThreadPoolExecutor as thread_pool

################################################################################

output_path = os.environ.get("OUT_HTML", "versions.html")

# If the cache file is older than this time (in seconds), regenerate it
upstream_cache_interval = 1 * 60 * 60
upstream_cache_path = os.environ.get("CACHE_FILE", "/tmp/pkg-versions-upstream-cache.json")

fedora_releases = ["f28", "f29", "f30", "f31", "f32", "f33"]
releases = fedora_releases + ["mbi", "mbi-bootstrap", "upstream (stable)"]

mbi_index = len(fedora_releases)
mbi_bootstrap_index = mbi_index + 1
upstream_index = mbi_bootstrap_index + 1

thread_pool_size = 30

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
	if not version:
		return ""
	
	version_name = version[:]
	version_name = version_name.replace("_", ".")
	version_name = version_name.replace("-", ".")
	
	# Match classical version symbols (numbers and dot)
	match = re.match("([.0-9]*[0-9]+)(.*)", version_name)
	
	if not match:
		raise BaseException("Invalid version name: " + version_name)
	
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
		lambda package: not package["blocked"], ks.listPackages("jp")
	)])

def get_upstream_version(package_name: str) -> (str, str):
	project_items = requests.get(
		f"https://release-monitoring.org/api/v2/packages/?name={package_name}&distribution=Fedora"
	).json()["items"]
	
	if len(project_items) == 0:
		print("Upstream project " + package_name + " not found")
		return ("", None)
	
	project_name = project_items[0]["project"]
	
	versions = requests.get(
		f"https://release-monitoring.org/api/v2/projects/?name={project_name}"
	).json()["items"][0]["versions"]
	
	latest_version = normalize_version(versions[0])
	
	# The first version not having a tilde in its normalized string
	latest_stable_version = None
	
	try:
		latest_stable_version = normalize_version(
			next((v for v in versions if not "~" in normalize_version(v)))
		)
	except:
		pass
	
	if latest_version == latest_stable_version:
		latest_stable_version = None
	
	return (latest_version, latest_stable_version)

def get_upstream_versions(package_names: [str]) -> {str: (str, str)}:
	result = {}
	
	pool = thread_pool(thread_pool_size)
	futures = list()
	
	for package_name in package_names:
		futures.append(pool.submit(get_upstream_version, package_name))
	
	for package_name, project_version in zip(package_names, futures):
		result[package_name] = project_version.result()
	
	return result

def read_json(filename: str) -> {str: str}:
	with open(filename, "r") as cache:
		return json.load(cache)

def write_json_timestamp(filename: str, packages: {str: str}):
	with open(filename, "w") as cache:
		result = {"time-retrieved": time.time(), "packages": packages}
		json.dump(result, cache, indent = 0)
		cache.write("\n")

def get_upstream_versions_cached(cache_path: str, package_names: [str]) -> {str: (str, str)}:
	update_cache = False
	result = {}
	
	if not os.path.exists(cache_path):
		update_cache = True
		
	else:
		cache = read_json(cache_path)
		
		if time.time() - cache["time-retrieved"] > upstream_cache_interval:
			update_cache = True
		
		else:
			result = cache["packages"]
	
	if update_cache:
		result = get_upstream_versions(package_names)
		write_json_timestamp(cache_path, result)
	
	return result

def get_koji_versions(package_names: [str], url: str, tag: str) -> {str : str}:
	ks = koji.ClientSession(url)
	ks.multicall = True
	for pkg in package_names:
		ks.listTagged(tag, package=pkg, latest=True)
	result = {}
	for [builds] in ks.multiCall(strict=True):
		if builds:
			result[builds[0]['package_name']] = builds[0]['version']
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
	content = requests.get("https://pagure.io/mbi/stage2/blob/master/f/project").content.decode("utf-8")
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
	result = {}
	
	pool = thread_pool(thread_pool_size)
	futures = list()
	
	def get_mbi_bootstrap_version(name: str) -> str:
		content = requests.get("https://pagure.io/mbi/stage2/raw/master/f/project/" + name + ".xml").content.decode("utf-8")
		
		version_str = "<version>"
		version_str_end = "</version>"
		
		begin = content.find(version_str) + len(version_str)
		end = content.find(version_str_end, begin)
		
		return content[begin : end]
	
	for package_name in package_names:
		futures.append(pool.submit(get_mbi_bootstrap_version, bootstrap_package_name.get(package_name) or package_name))
	
	for package_name, project_version in zip(package_names, futures):
		result[package_name] = project_version.result()
	
	return result

def get_all_versions() -> {str: []}:
	result = {}
	
	package_names = get_packages()
	
	upstream = get_upstream_versions_cached(upstream_cache_path, package_names)
	mbi = get_mbi_versions(package_names)
	mbi_bootstrap = get_mbi_bootstrap_packages()
	
	mbi_bootstrap = get_mbi_bootstrap_versions({name for name in package_names
		if name in mbi_bootstrap or bootstrap_package_name.get(name) in mbi_bootstrap
	})
	
	releases = {}
	
	pool = thread_pool(len(fedora_releases))
	futures = list()
	
	for release in fedora_releases:
		futures.append(pool.submit(get_fedora_versions, package_names, release))
	
	for release, release_versions in zip(fedora_releases, futures):
		releases[release] = release_versions.result()
	
	for package_name in sorted(package_names):
		result[package_name] = list()
		for release in fedora_releases:
			result[package_name].append(releases[release][package_name])
		result[package_name].append(mbi[package_name])
		
		# Get None if package is not listed
		result[package_name].append(mbi_bootstrap.get(package_name))
		
		result[package_name].append(upstream[package_name])
	
	return result

def version_compare(left: str, right: str) -> int:
	return rpm.labelCompare(("", left, ""), ("", right, ""))

def row_to_str(versions: [str], tags: {str : str}) -> str:
	assert(len(versions) == len(releases))
	
	result = str()
	html_class = str()
	fedora_index = 0
	
	while fedora_index < mbi_index:
		colspan = 1
		while fedora_index + 1 < mbi_index and version_compare(versions[fedora_index], versions[fedora_index + 1]) == 0:
			colspan += 1
			fedora_index += 1
		
		html_class = "fedora"
		result += '<td '
		
		if colspan > 1:
			result += 'colspan="' + str(colspan) + '" '
		
		result += 'class="' + html_class + '">' + versions[fedora_index] + '</td>\n'
		fedora_index += 1
	
	html_class = "mbi"
	colspan = None
	result += '<td class="' + html_class + '">' + versions[mbi_index] + '</td>\n'
	
	compare_value = version_compare(versions[mbi_index], versions[upstream_index][0])
	
	if versions[upstream_index] == "":
		html_class = "unknown-version"
	elif "keep-version" in tags and version_compare(versions[mbi_index], tags["keep-version"]) == 0:
		html_class = "keep-version"
	elif "correct-version" in tags and version_compare(versions[mbi_index], tags["correct-version"]) == 0:
		html_class = "correct-version"
	elif compare_value == 0:
		html_class = "up-to-date"
	elif compare_value < 0:
		html_class = "downgrade"
	elif compare_value > 0:
		html_class = "mbi-newer"
	
	result += '<td class="' + "mbi-bootstrap" + '">' + (versions[mbi_bootstrap_index] or "") + '</td>\n'
	result += '<td '
	
	if versions[upstream_index][1] is None:
		result += 'colspan="2" '
	
	result += 'class="' + html_class + '">' + versions[upstream_index][0] + '</td>\n'
	
	if not versions[upstream_index][1] is None:
		html_stable_class = "unknown-version"
		
		latest_stable_compare_value = version_compare(versions[mbi_index], versions[upstream_index][1])
		
		if latest_stable_compare_value == 0:
			html_stable_class = "stable-up-to-date"
		elif latest_stable_compare_value < 0:
			html_stable_class = "downgrade"
		elif latest_stable_compare_value > 0:
			html_stable_class = "mbi-newer"
			
		result += '<td class="' + html_stable_class + '">' + versions[upstream_index][1] + '</td>\n'
	
	return result

def get_comments(package_names: [str]) -> ({str : str}, {str : {str : str}}):
	request = requests.get(
		"https://pagure.io/java-pkg-versions-comments/raw/master/f/comments.md",
		timeout = 7)
	
	if request.status_code != 200:
		raise RuntimeError("Could not obtain comments")
	
	result = {package_name: "" for package_name in package_names}
	tags = {package_name: "" for package_name in package_names}
	name = str()
	comment = str()

	for line in request.text.splitlines():
		# A new package name
		if line.startswith("#") and not line.startswith("##"):
			name = line[1:].strip()
			tags[name] = dict()
		
		# A new tag
		elif line.startswith("##"):
			if name:
				match = re.match("##\\s*(.*?)\\s*:\\s*(.*)", line)
				tags[name][match.group(1)] = match.group(2).rstrip()
		
		# End of the comment for the current package name
		elif line.startswith("---") or (line.startswith("#") and not line.startswith("##") and name):
			if name:
				match = re.match("<p>(.*)</p>\\s*", markdown2.markdown(comment), re.DOTALL)
				result[name] = match.group(1)
			name = str()
			comment = str()
		
		elif name:
			comment += line
			comment += "\n"
	
	return result, tags

################################################################################

# Tests

assert(normalize_version("") == "")
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

# Main function

versions_all = None
comments_all = None
tags_all = None

# Retry a few times if an exception occurs
for i in range(3):
	try:
		versions_all = get_all_versions() if versions_all is None else versions_all
		comments_all, tags_all = get_comments(versions_all.keys())
		break
	except:
		continue

with open(output_path, "w") as table:
	table.write('<link rel=stylesheet href=mystyle.css>')
	table.write('<table>\n')
	
	table.write('<th>' + 'Package name' + '</th>\n')
	
	for header_name in releases[:-1]:
		table.write('<th>' + header_name + '</th>\n')
	
	table.write('<th colspan="2">' + releases[-1] + '</th>\n')
	
	table.write('<th>' + 'Comment' + '</th>\n')
	
	table.write('<th>' + 'Links' + '</th>\n')
	
	for pkg_name, version_list in versions_all.items():
		table.write('<tr>\n')
		
		# Package name
		table.write('<td>' + pkg_name + '</td>\n')
		
		# Versions
		table.write(row_to_str(version_list, tags_all[pkg_name]))
		
		# Comment
		table.write('<td>\n')
		table.write(comments_all[pkg_name])
		table.write('</td>\n')
		
		# Links
		table.write('<td>\n')
		table.write('MBI\n')
		table.write('(<a href="https://src.fedoraproject.org/fork/mbi/rpms/' + pkg_name + '" target="_blank">dist-git</a>)\n')
		table.write('(<a href="https://koji.kjnet.xyz/koji/packageinfo?packageID=' + pkg_name + '" target="_blank">Koji</a>)\n')
		table.write('(<a href="https://koschei.kjnet.xyz/koschei/package/' + pkg_name + '?collection=jp" target="_blank">Koschei</a>)\n')
		table.write('</td>\n')
		
		table.write('</tr>\n')
	table.write('</table>\n')
	table.write('<p>Generated on ' + time.ctime() + ' by ' + os.environ["HOSTNAME"] + '</p>\n')
