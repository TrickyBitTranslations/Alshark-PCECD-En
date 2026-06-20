# Alshark disassembly/reassembly rebuild (wla-dx HuC6280).
# Needs wla-huc6280 + wlalink on PATH (built from vhelin/wla-dx), plus chdman for `chd`.
# Bring your own disc cooked to ../work/track02.iso (see tools/cook.py); build.py carves the
# original bank bytes out of it automatically - they are never committed.

.PHONY: all build selftest disc chd clean

all: build

# carve + assemble + splice the font and translated script
build:
	python3 build.py

# disassembler round-trip: prove we can reproduce the ORIGINAL bytes byte-identical
selftest:
	python3 build.py --selftest

# also emit a patched BIN/CUE in build/
disc:
	python3 build.py --disc

# also build the patched CHD
chd:
	python3 build.py --chd

clean:
	rm -f build/*.o build/*.bin build/*.link
