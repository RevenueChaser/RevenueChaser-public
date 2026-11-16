"""The profile's prompt, parser, chunker and merge moved to ``rcdata/sec_profile.py`` (#894): the SEC reading
service owns the question, and ``rcdata`` never imports a board. This name is that module itself, not a copy, so
``profile_v3.SYSTEM``, a private helper or a test's patch reach the one object.
"""
import sys

from ..rcdata import sec_profile as _moved

sys.modules[__name__] = _moved
