#!/usr/bin/env python3

import argparse
import logging
import time
import xml.etree.ElementTree as ET

XMLNS = {'': 'http://www.tei-c.org/ns/1.0',
         'xml': 'http://www.w3.org/XML/1998/namespace'}

def ns_name(ns, name):
    return f"{{{XMLNS[ns]}}}{name}"

def load_xml_file(args):
    """
    Load inputfile
    """
    infilename = args.inputfile
    logging.info(f"Loading XML file {infilename}")
    next_time = time.time()
    tree = ET.parse(infilename)
    return tree.getroot()

def parse_div(doc, level):
    div_id = doc.get(ns_name('xml', 'id'))
    div_type = doc.get('type')
    headtexts = []
    heads = doc.findall('head', XMLNS)
    if heads:
        for head in heads:
            headtexts.append(''.join(head.itertext()))

    headtext = ' '.join(headtexts)
    
    subdivs = doc.findall('div', XMLNS)
    subdiv_infos = []
    if subdivs:
        for subdiv in subdivs:
            subdiv_infos.append(parse_div(subdiv, level + 1))
        
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


def parse_tei(doc):
    if doc.tag != ns_name('', 'TEI'):
        raise RuntimeError("Not a valid TEI document: root element is not 'TEI'")
    
    text = doc.find('text', XMLNS)
    if not text:
        raise RuntimeError("Not a valid TEI document: missing 'text' element")
        
    infos = []
    front = text.find('front', XMLNS)
    if front:
        for div in front.findall('div', XMLNS):
            infos.append(parse_div(div, 1))

    body = text.find('body', XMLNS)
    if body:
        for div in body.findall('div', XMLNS):
            infos.append(parse_div(div, 1))

    back = text.find('back', XMLNS)
    if back:
        for div in back.findall('div', XMLNS):
            infos.append(parse_div(div, 1))

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
 
    args = argp.parse_args()
    
    # set up 
    logging.basicConfig(level=args.loglevel)

    doc = load_xml_file(args)
    info = parse_tei(doc)
    logging.debug(f"infos={info}")


if __name__ == '__main__':
    main()
