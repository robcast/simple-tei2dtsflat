#!/usr/bin/env python3

import argparse
import logging
import time
import xml.etree.ElementTree as ET
from pathlib import Path
import xml

XMLNS = {'': 'http://www.tei-c.org/ns/1.0',
         'xml': 'http://www.w3.org/XML/1998/namespace',
         'dts': 'https://w3id.org/dts/api#'}

for n in XMLNS:
    ET.register_namespace(n, XMLNS[n])

def ns_name(ns, name):
    return f"{{{XMLNS[ns]}}}{name}"


def write_document(doc, basedir):
    """
    Write document doc as XML file in basedir.
    """
    dir = Path(basedir)
    dir.mkdir(parents=True, exist_ok=True)
    outfile = Path(dir, 'tei-doc.xml')
    with outfile.open(mode='wb') as f:
        # write as new ElementTree
        tree = ET.ElementTree(doc)
        tree.write(f, encoding='utf-8', xml_declaration=True)        


def write_fragment(doc, basedir, level, frag_id, args):
    """
    Write fragment doc as XML file in structured directories starting at basedir.
    
    Directory structure: basedir/level/frag_id/tei-frag.xml
    """
    dir = Path(basedir, str(level), frag_id)
    dir.mkdir(parents=True, exist_ok=True)
    outfile = Path(dir, 'tei-frag.xml')
    with outfile.open(mode='wb') as f:
        # root element TEI
        tei = ET.Element('TEI')
        # dts:fragment wrapper around fragment doc
        frag = ET.SubElement(tei, ns_name('dts', 'fragment'))
        frag.append(doc)
        # write as new ElementTree
        tree = ET.ElementTree(tei)
        tree.write(f, encoding='utf-8', xml_declaration=True)
        

def load_xml_file(args):
    """
    Load and parse args.inputfile. 
    
    Returns etree root Element.
    """
    infilename = args.inputfile
    logging.info(f"Loading XML file {infilename}")
    next_time = time.time()
    tree = ET.parse(infilename)
    return tree.getroot()


def parse_div(doc, level, args):
    """
    Parse TEI div structure in doc Element (recursively). 
    
    Writes div fragment files.
    Returns info dict. 
    """
    div_id = doc.get(ns_name('xml', 'id'))
    if div_id is None:
        div_id = f"id-div{args.id_cnt}"
        args.id_cnt += 1
        doc.set(ns_name('xml', 'id'), div_id)
        
    div_type = doc.get('type')
    headtexts = []
    heads = doc.findall('head', XMLNS)
    if heads:
        for head in heads:
            headtexts.append(''.join(head.itertext()))

    headtext = ' '.join(headtexts)
    
    # write div fragment to file
    write_fragment(doc, args.basedir, level, div_id, args)
    
    # process sub-divs
    subdivs = doc.findall('div', XMLNS)
    subdiv_infos = []
    if subdivs:
        for subdiv in subdivs:
            subdiv_infos.append(parse_div(subdiv, level+1, args))
        
    logging.debug(f"div level={level} id={div_id} type={div_type}")
    logging.debug(f"  head: {headtext}")
    
    info = {
        'level': level,
        'id': div_id,
        'type': div_type,
        'head': headtext,
        'subdivs': subdiv_infos
    }
    return info


def parse_tei(doc, args):
    """
    Parse TEI document in doc Element.
    
    Returns list of info structures from divs.
    """
    if doc.tag != ns_name('', 'TEI'):
        raise RuntimeError("Not a valid TEI document: root element is not 'TEI'")
    
    text = doc.find('text', XMLNS)
    if not text:
        raise RuntimeError("Not a valid TEI document: missing 'text' element")
    
    # write full document to basedir
    write_document(doc, args.basedir)
    
    infos = []
    front = text.find('front', XMLNS)
    if front:
        for div in front.findall('div', XMLNS):
            infos.append(parse_div(div, 1, args))

    body = text.find('body', XMLNS)
    if body:
        for div in body.findall('div', XMLNS):
            infos.append(parse_div(div, 1, args))

    back = text.find('back', XMLNS)
    if back:
        for div in back.findall('div', XMLNS):
            infos.append(parse_div(div, 1, args))

    return infos

##
## main
##
def main():
    argp = argparse.ArgumentParser(description='Create DTSflat file structure from TEI XML.')
    argp.add_argument('--version', action='version', version='%(prog)s 0.0')
    argp.add_argument('-l', '--log', dest='loglevel', choices=['INFO', 'DEBUG', 'ERROR'], default='DEBUG', 
                      help='Log level.')
    argp.add_argument('inputfile',
                      help='TEI XML input file.')
    argp.add_argument('-b', '--base-dir', dest='basedir', default='dts-dir', 
                      help='DTSflat output base directory.')
 
    args = argp.parse_args()
    
    # set up 
    logging.basicConfig(level=args.loglevel)
    args.id_cnt = 1

    doc = load_xml_file(args)
    info = parse_tei(doc, args)
    logging.debug(f"infos={info}")


if __name__ == '__main__':
    main()
