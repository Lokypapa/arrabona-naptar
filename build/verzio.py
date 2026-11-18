# A build.bat hivja: kiirja a VERSION erteket az anaptar/__init__.py-bol.
import os
import re
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "anaptar", "__init__.py")
with open(p, encoding="utf-8") as f:
    print(re.search(r'^VERSION = "(.+?)"', f.read(), re.M).group(1))
