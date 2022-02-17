# Simple tei2dtsflat

Simple Python tool to create a DTSflat file structure from a (simple) TEI XML file.

The generated DTSflat files can be used to serve a [DTS API](https://distributed-text-services.github.io/specifications/) using the minimal computing https://github.com/robcast/dtsflat-server

Requirements
- Python3 (>3.6)

```
usage: tei2dtsflat.py [-h] [--version] [-l {INFO,DEBUG,ERROR}] [-b BASEDIR] [-i DOCID]
                      [--gen-id-prefix GENID_PREFIX] [-u URL_PREFIX] [--document-prefix DOC_PREFIX]
                      [--navigation-prefix NAV_PREFIX] [-m {div}]
                      inputfile

Create DTSflat file structure from TEI XML.

positional arguments:
  inputfile             TEI XML input file.

optional arguments:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -l {INFO,DEBUG,ERROR}, --log {INFO,DEBUG,ERROR}
                        Log level.
  -b BASEDIR, --base-dir BASEDIR
                        DTSflat output base directory.
  -i DOCID, --document-id DOCID
                        DTS main document id (default: inputfile).
  --gen-id-prefix GENID_PREFIX
                        Prefix for generated xml-ids.
  -u URL_PREFIX, --url-prefix URL_PREFIX
                        DTS API base URL prefix.
  --document-prefix DOC_PREFIX
                        DTS document endpoint URL prefix (below base URL).
  --navigation-prefix NAV_PREFIX
                        DTS navigation endpoint URL prefix (below base URL).
  -m {div}, --navigation-mode {div}
                        Type of navigation structure: div=by tei:div.
```
