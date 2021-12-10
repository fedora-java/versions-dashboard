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

import re

def normalize(version: str) -> str:
    version_name = version[:]
    version_name = version_name.replace("_", ".")
    version_name = version_name.replace("-", ".")
    
    # Match the usual version symbols (numbers and dot)
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

################################################################################

assert(normalize("1.0b3") == "1.0~b3")
assert(normalize("2.5.0-rc1") == "2.5.0~rc1")
assert(normalize("2.0b6") == "2.0~b6")
assert(normalize("2.0.SP1") == "2.0.SP1")
assert(normalize("3_2_12") == "3.2.12")
assert(normalize("1.0-20050927.133100") == "1.0.20050927.133100")
assert(normalize("3.0.1-b11") == "3.0.1~b11")
assert(normalize("5.0.1-b04") == "5.0.1~b04")
assert(normalize("0.11b") == "0.11b")
assert(normalize("1_6_2") == "1.6.2")
assert(normalize("1.0.1.Final") == "1.0.1")
assert(normalize("3.0.0.M1") == "3.0.0~M1")
assert(normalize("6.0-alpha-2") == "6.0~alpha.2")
assert(normalize("4.13-beta-1") == "4.13~beta.1")
assert(normalize("5.5.0-M1") == "5.5.0~M1")
assert(normalize("3.0.0-M2") == "3.0.0~M2")
assert(normalize("3.0.0-M1") == "3.0.0~M1")
assert(normalize("3.0.0-M3") == "3.0.0~M3")
assert(normalize("3.0.0-beta.1") == "3.0.0~beta.1")
assert(normalize("1.0-alpha-2.1") == "1.0~alpha.2.1")
assert(normalize("1.0-alpha-8") == "1.0~alpha.8")
assert(normalize("1.0-alpha-18") == "1.0~alpha.18")
assert(normalize("1.0-alpha-10") == "1.0~alpha.10")
assert(normalize("1.0-beta-7") == "1.0~beta.7")
assert(normalize("1.0-alpha-5") == "1.0~alpha.5")
assert(normalize("2.0-M10") == "2.0~M10")
assert(normalize("7.0.0-beta4") == "7.0.0~beta4")
