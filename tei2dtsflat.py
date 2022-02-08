#!/usr/bin/env python3

import argparse
import logging
import time
import xml.etree.ElementTree as ET
from pathlib import Path
import xml
import json

XMLNS = {'': 'http://www.tei-c.org/ns/1.0',
         'xml': 'http://www.w3.org/XML/1998/namespace',
         'dts': 'https://w3id.org/dts/api#'}

for n in XMLNS:
    ET.register_namespace(n, XMLNS[n])

def ns_name(ns, name):
    return f"{{{XMLNS[ns]}}}{name}"


def write_xml_document(doc, args):
    """
    Write document doc as XML file in basedir/docid.
    """
    dir = Path(args.basedir, args.docid)
    dir.mkdir(parents=True, exist_ok=True)
    outfile = Path(dir, 'tei-doc.xml')
    logging.debug(f"writing XML document {outfile}")
    with outfile.open(mode='wb') as f:
        # write as new ElementTree
        tree = ET.ElementTree(doc)
        tree.write(f, encoding='utf-8', xml_declaration=True)        


def write_xml_fragment(doc, frag_id, args):
    """
    Write fragment doc as XML file in structured directories starting at basedir.
    
    Directory structure: basedir/docid/frag_id/tei-frag.xml
    """
    dir = Path(args.basedir, args.docid, frag_id)
    dir.mkdir(parents=True, exist_ok=True)
    outfile = Path(dir, 'tei-frag.xml')
    logging.debug(f"writing XML fragment {outfile}")
    with outfile.open(mode='wb') as f:
        # root element TEI
        tei = ET.Element('TEI')
        # dts:fragment wrapper around fragment doc
        frag = ET.SubElement(tei, ns_name('dts', 'fragment'))
        frag.append(doc)
        # write as new ElementTree
        tree = ET.ElementTree(tei)
        tree.write(f, encoding='utf-8', xml_declaration=True)
        

def write_json_document(doc, level, args):
    """
    Write document doc as JSON file in basedir/docid.
    """
    if level == 0:
        dir = Path(args.basedir, args.docid)
    else:
        dir = Path(args.basedir, args.docid, str(level))
        
    dir.mkdir(parents=True, exist_ok=True)
    outfile = Path(dir, 'dts-nav.json')
    logging.debug(f"writing JSON document {outfile}")
    with outfile.open(mode='w', encoding='utf-8') as f:
        json.dump(doc, f)       


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


def parse_tei_div(doc, level, args):
    """
    Parse TEI div structure in doc Element (recursively). 
    
    Writes div fragment files.
    Returns info dict. 
    """
    div_id = doc.get(ns_name('xml', 'id'))
    if div_id is None:
        # create and set new id
        div_id = f"{args.genid_prefix}-div{args.genid_cnt}"
        args.genid_cnt += 1
        doc.set(ns_name('xml', 'id'), div_id)
        
    div_type = doc.get('type')
    
    # collect the text from all head tags
    headtexts = []
    heads = doc.findall('head', XMLNS)
    if heads:
        for head in heads:
            headtexts.append(''.join(head.itertext()))

    headtext = ' '.join(headtexts)
    
    # write div fragment to file
    write_xml_fragment(doc, div_id, args)
    
    # collect all sub-divs
    subdivs = doc.findall('div', XMLNS)
    subdiv_infos = []
    if subdivs:
        for subdiv in subdivs:
            subdiv_infos.append(parse_tei_div(subdiv, level+1, args))
        
    logging.debug(f"div level={level} id={div_id} type={div_type} heads: {headtext}")
    
    info = {
        'level': level,
        'id': div_id,
        'type': div_type,
        'head': headtext,
        'subdivs': subdiv_infos
    }
    return info


def parse_tei_doc(doc, args):
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
    write_xml_document(doc, args)
    
    infos = []
    front = text.find('front', XMLNS)
    if front:
        for div in front.findall('div', XMLNS):
            infos.append(parse_tei_div(div, 1, args))

    body = text.find('body', XMLNS)
    if body:
        for div in body.findall('div', XMLNS):
            infos.append(parse_tei_div(div, 1, args))

    back = text.find('back', XMLNS)
    if back:
        for div in back.findall('div', XMLNS):
            infos.append(parse_tei_div(div, 1, args))

    return infos


def get_div_maxlevel(infos, maxlevel):
    """
    Returns the maximum div level.
    """
    for info in infos:
        if info['level'] > maxlevel:
            maxlevel = info['level']
            
        if info['subdivs']:
            maxlevel = get_div_maxlevel(info['subdivs'], maxlevel)
            
    return maxlevel


def get_div_ids(infos, level):
    """
    Returns a list of all div ids at level.
    """
    ids = []
    for info in infos:
        if info['level'] == level:
            ids.append(info['id'])
            
        if info['subdivs']:
            subids = get_div_ids(info['subdivs'], level)
            ids.extend(subids)
            
    return ids


def write_nav_level(infos, level, args):
    """
    Write DTS navigation structure JSON file for level.
    """
    nav_struct = {
        '@context': {
            '@vocab': 'https://www.w3.org/ns/hydra/core#',
            'dts': 'https://w3id.org/dts/api#'
        },
        '@id': f"{args.url_prefix}/navigation/?id={args.docid}&level={level}",
        'dts:citeDepth': args.cite_depth,
        'dts:level': level,
        'member': [{'dts:ref': ref} for ref in get_div_ids(infos, level)],
        'dts:passage': f"{args.url_prefix}/documents/?id={args.docid}{{&ref}}",
        'dts:parent': None
    }
    write_json_document(nav_struct, level, args)


def write_nav_ref(infos, ref, level, args):
    """
    Write DTS navigation structure JSON file for ref.
    """
    nav_struct = {
        '@context': {
            '@vocab': 'https://www.w3.org/ns/hydra/core#',
            'dts': 'https://w3id.org/dts/api#'
        },
        '@id': f"{args.url_prefix}/navigation/?id={args.docid}&ref={ref}&level={level}",
        'dts:citeDepth': args.cite_depth,
        'dts:level': level,
        'member': [{'dts:ref': ref} for ref in get_div_ids(infos, level)],
        'dts:passage': f"{args.url_prefix}/documents/?id={args.docid}{{&ref}}",
        'dts:parent': None
    }
    write_json_document(nav_struct, level, args)


def write_navigation(infos, args):
    """
    Write DTS navigation structure JSON files.
    """
    args.cite_depth = get_div_maxlevel(infos, 0)
    # write navigation for levels
    for level in range(1, args.cite_depth+1):
        write_nav_level(infos, level, args)
   
    # write navigation for refs
    
    
##
## main
##
def main():
    argp = argparse.ArgumentParser(description='Create DTSflat file structure from TEI XML.')
    argp.add_argument('--version', action='version', version='%(prog)s 0.1')
    argp.add_argument('-l', '--log', dest='loglevel', choices=['INFO', 'DEBUG', 'ERROR'], default='DEBUG', 
                      help='Log level.')
    argp.add_argument('inputfile',
                      help='TEI XML input file.')
    argp.add_argument('-b', '--base-dir', dest='basedir', default='dts-dir', 
                      help='DTSflat output base directory.')
    argp.add_argument('-i', '--document-id', dest='docid', 
                      help='DTS main document id (default: inputfile).')
    argp.add_argument('--gen-id-prefix', dest='genid_prefix', default='genid',
                      help='Prefix for generated xml-ids.')
    argp.add_argument('-u', '--url-prefix', dest='url_prefix', default='/dts',
                      help='DTS API URL prefix.')
 
    args = argp.parse_args()
    
    # set up 
    logging.basicConfig(level=args.loglevel)
    if args.docid is None:
        docid = args.inputfile.lower().replace('.tei', '').replace('.xml', '')
        args.docid = docid
        
    # global counter for generated ids
    args.genid_cnt = 1

    # load and process inputfile into document endpoint structure
    doc = load_xml_file(args)
    logging.info("Parsing TEI document and creating document endpoint structure...")
    info = parse_tei_doc(doc, args)
    #logging.debug(f"infos={info}")
    # write navigation endpoint structure
    logging.info("Creating navigation endpoint structure...")
    write_navigation(info, args)


if __name__ == '__main__':
    main()
