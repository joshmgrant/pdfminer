# Makefile for pdfminer

PACKAGE=pdfminer

SVN=svn
GNUTAR=tar
PYTHON=python
TMPDIR=/tmp
VERSION=`$(PYTHON) $(PACKAGE)/__init__.py`
DISTNAME=$(PACKAGE)-dist-$(VERSION)
DISTFILE=$(DISTNAME).tar.gz

CONV_CMAP=$(PYTHON) pdfminer/cmap.py

all:

install:
	$(PYTHON) setup.py install

clean:
	-rm -rf build
	-cd $(PACKAGE) && $(MAKE) clean
	-cd tools && $(MAKE) clean
	-cd samples && $(MAKE) clean

test:
	cd samples && $(MAKE) test

# Maintainance:
commit: clean
	$(SVN) commit

check:
	cd $(PACKAGE) && make check

dist: clean
	$(SVN) cleanup
	$(SVN) export . $(TMPDIR)/$(DISTNAME)
	$(GNUTAR) c -z -C$(TMPDIR) -f $(TMPDIR)/$(DISTFILE) $(DISTNAME) --dereference --numeric-owner
	-rm -rf $(TMPDIR)/$(DISTNAME)

WEBDIR=$$HOME/Site/unixuser.org/python/pdfminer
publish: dist
	cp $(TMPDIR)/$(DISTFILE) $(WEBDIR)
	cp README.html $(WEBDIR)/index.html
