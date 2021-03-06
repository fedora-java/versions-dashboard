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

import jinja2
import json
import os
import rpm

################################################################################

input_path = os.environ.get("OUT_JSON", "versions.json")
output_path = os.environ.get("OUT_HTML", "versions.html")
template_path = "versions-template.html"

################################################################################

def version_compare(left: str, right: str) -> int:
	return rpm.labelCompare(("", left, ""), ("", right, ""))

################################################################################

with open(input_path, "r") as input_file:
	report_dict = json.load(input_file)

env = jinja2.Environment(loader = jinja2.FileSystemLoader("."))
env.globals.update(vars(__builtins__))
env.globals.update(globals())

template = env.get_template(template_path)
output = template.render(report_dict = report_dict)

with open(output_path, "w") as output_file:
	output_file.write(output)
