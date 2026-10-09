"""Maintenance scripts, importable so their expectations can be tested.

`make_common_passwords` holds the table of passwords that must be refused and must be
accepted. The tests import it rather than keeping a second copy, because a second copy is
how the generated browser fixture and the Python's own test end up disagreeing.
"""
