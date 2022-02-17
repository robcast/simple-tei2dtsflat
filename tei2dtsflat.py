#!/usr/bin/env python3

import argparse
import logging
import time
import xml.etree.ElementTree as ET
import xml.sax
from pathlib import Path
import json

XMLNS = {'': 'http://www.tei-c.org/ns/1.0',
         'xml': 'http://www.w3.org/XML/1998/namespace',
         'dts': 'https://w3id.org/dts/api#'}

for n in XMLNS:
    ET.register_namespace(n, XMLNS[n])

def ns_name(ns, lname):
    return f"{{{XMLNS[ns]}}}{lname}"

def q_name(ns, lname):
    if ns is None or ns == XMLNS['']:
        return lname
    else:
        return f"{{{ns}}}{lname}"


def write_xml_document(doc, args):
    """
    Write document doc as XML file in basedir/docid.
    """
    dir = Path(args.basedir, args.docid)
    dir.mkdir(parents=True, exist_ok=True)
    outfile = Path(dir, 'tei-full.xml')
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
        # root fragment_root TEI
        tei = ET.Element('TEI')
        # dts:fragment wrapper around fragment doc
        frag = ET.SubElement(tei, ns_name('dts', 'fragment'))
        frag.append(doc)
        # write as new ElementTree
        tree = ET.ElementTree(tei)
        tree.write(f, encoding='utf-8', xml_declaration=True)
        

def write_json_document(doc, ref, level, args):
    """
    Write document doc as JSON file in basedir/docid.
    """
    if level == 0 and ref is None:
        dir = Path(args.basedir, args.docid)
    elif level == 0:
        # directories for ref only
        dir = Path(args.basedir, args.docid, ref)
    elif ref is None:
        # directories for level only
        dir = Path(args.basedir, args.docid, str(level))
    else:
        # directories for ref and level
        dir = Path(args.basedir, args.docid, ref, str(level))
        
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
    logging.info(f"Loading XML file {args.inputfile}")
    tree = ET.parse(args.inputfile)
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
        raise RuntimeError("Not a valid TEI document: root fragment_root is not 'TEI'")
    
    text = doc.find('text', XMLNS)
    if not text:
        raise RuntimeError("Not a valid TEI document: missing 'text' fragment_root")
    
    # write full document to basedir
    write_xml_document(doc, args)
    
    infos = []
    if args.nav_mode == 'div':
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
        
    elif args.nav_mode == 'pb':
        infos.append(parse_tei_pbs(args))
        
    else:
        raise RuntimeError(f"Invalid navigation mode {args.nav_mode}")
    
    return infos


def parse_tei_pbs(args):
    """
    Parse TEI document in args.inputfile for pb elements.
    
    Writes XML fragments between pb elements.
    Returns list of info structures from pbs. 
    """
    
    class TeiPbHandler(xml.sax.handler.ContentHandler):
    
        def __init__(self, args):
            self.args = args
            self.pbs = []
            self.fragment_root = ET.Element('TEI')
            self.current_element = self.fragment_root
            self.current_parent = None
            self.pb_cnt = 0
            self.params = {}
    
        def create_etree_elem(self, sax_name, sax_attrs):
            ns, lname = sax_name
            attrs = {q_name(k[0], k[1]): sax_attrs[k] for k in sax_attrs}
            elem = ET.Element(q_name(sax_name[0], sax_name[1]), attrib=attrs)
            return elem
    
        def start_etree_fragment(self, elem):
            self.fragment_root = ET.Element('TEI')
            self.fragment_root.append(elem)
            self.current_element = elem
            self.current_parent = self.fragment_root
    
        def write_etree_fragment(self, pb):
            write_xml_fragment(self.fragment_root, pb['id'], self.args)
    
        def startElementNS(self, name, qname, attrs):
            ns, lname = name
            elem = self.create_etree_elem(name, dict(attrs))
            if lname == 'pb':
                # write previous fragment
                if len(self.pbs) > 0:
                    self.write_etree_fragment(self.pbs[-1])
                    
                # start new fragment
                self.pb_cnt += 1
                pb_id = f"pb-{self.pb_cnt}"
                self.start_etree_fragment(elem)
                facs = attrs.getValueByQName('facs')
                if facs is None:
                    logging.warning("pb tag without facs attribute")
                    
                self.pbs.append({'id': pb_id, 'facs': facs, 'attrs': dict(attrs)})
                
            else:
                # append current element to fragment
                self.current_parent = self.current_element
                self.current_parent.append(elem)
                self.current_element = elem
    
        def characters(self, content):
            if self.current_element.text is None:
                self.current_element.text = content.strip()
            else:
                self.current_element.text += content.strip()
    
        def endElementNS(self, name, qname):
            # close current element
            self.current_element = self.current_parent
            if self.current_element is None:
                logging.warning(f"empty stack after closing element {name}")
                
        def endDocument(self):
            # save last fragment
            pass
    
        def getParams(self):
            return self.params
        
    # create SAX parser
    parser = xml.sax.make_parser()
    parser.setFeature(xml.sax.handler.feature_namespaces, True)
    # set our handler
    handler = TeiPbHandler(args)
    parser.setContentHandler(handler)
    # parse XML file
    parser.parse(args.inputfile)
    # get output from handler
    params = handler.getParams()


def get_maxlevel(divs, maxlevel):
    """
    Returns the maximum div level.
    """
    for info in divs:
        if info['level'] > maxlevel:
            maxlevel = info['level']
            
        if info['subdivs']:
            maxlevel = get_maxlevel(info['subdivs'], maxlevel)
            
    return maxlevel


def get_div_by_ref(divs, ref):
    """
    Returns the div with the id ref.
    """
    refdiv = None
    parent_id = None
    for div in divs:
        if div['id'] == ref:
            refdiv = div
            break

        if div['subdivs']:
            subdiv, _ = get_div_by_ref(div['subdivs'], ref)
            if subdiv:
                refdiv = subdiv
                parent_id = div['id']
                break

    return refdiv, parent_id


def get_div_ids_by_level(divs, level):
    """
    Returns a list of all div ids with level.
    """
    if not isinstance(divs, list):
        divs = [divs]
    
    ids = []
    for div in divs:
        if div['level'] == level:
            ids.append(div['id'])
            # no need to check subdivs
            continue
        
        elif div['level'] > level:
            # no need to check at this level
            return ids
            
        if div['subdivs']:
            subids = get_div_ids_by_level(div['subdivs'], level)
            ids.extend(subids)
            
    return ids


def get_div_ids_upto_level(divs, level):
    """
    Returns a list of all div ids up to level.
    """
    if not isinstance(divs, list):
        divs = [divs]
        
    ids = []
    for div in divs:
        if div['level'] < level:
            ids.append(div['id'])
            
        elif div['level'] == level:
            ids.append(div['id'])
            # no need to check subdivs
            continue
        
        elif div['level'] > level:
            # no need to check at this level
            return ids

        if div['subdivs']:
            subids = get_div_ids_upto_level(div['subdivs'], level)
            ids.extend(subids)
            
    return ids


def write_nav_doc_level(divs, level, args):
    """
    Write DTS navigation structure JSON file for full document at level.
    """
    members = get_div_ids_by_level(divs, level)
    if not members:
        return 
    
    if level > 1:
        level_param = '&level=' + str(level)
        parent = {
            '@type': 'Resource', 
            '@dts:ref': f"{args.url_prefix}{args.nav_prefix}?id={args.docid}"
        }

    else:
        level_param = ''
        parent = None
        
    nav_struct = {
        '@context': {
            '@vocab': 'https://www.w3.org/ns/hydra/core#',
            'dts': 'https://w3id.org/dts/api#'
        },
        '@id': f"{args.url_prefix}{args.nav_prefix}?id={args.docid}{level_param}",
        'dts:citeDepth': args.cite_depth,
        'dts:level': level,
        'member': [{'dts:ref': div_id} for div_id in members],
        'dts:passage': f"{args.url_prefix}{args.doc_prefix}?id={args.docid}{{&ref}}",
        'dts:parent': parent
    }
    write_json_document(nav_struct, None, level, args)
    # write level 1 also as toplevel
    if level == 1:
        write_json_document(nav_struct, None, 0, args)


def write_nav_ref_level(divs, ref, level, args):
    """
    Write DTS navigation structure JSON file for fragment ref at level.
    """
    div, parent_id = get_div_by_ref(divs, ref)
    if div is None:
        raise RuntimeError(f"div for ref={ref} not found!")

    
    reflevel = div['level']
    if level == reflevel:
        # no members at same level
        return
    
    members = get_div_ids_by_level(div, level)
    if not members:
        return 

    # create parent nav link
    if reflevel == 1:
        parent = {
            '@type': 'Resource', 
            '@dts:ref': f"{args.url_prefix}{args.nav_prefix}?id={args.docid}"
        }
    elif reflevel > 1:
        parent = {
            '@type': 'CitableUnit', 
            '@dts:ref': parent_id
        }
    else:
        parent = None
    
    nav_struct = {
        '@context': {
            '@vocab': 'https://www.w3.org/ns/hydra/core#',
            'dts': 'https://w3id.org/dts/api#'
        },
        '@id': f"{args.url_prefix}{args.nav_prefix}?id={args.docid}&ref={ref}",
        'dts:citeDepth': args.cite_depth,
        'dts:level': level,
        'member': [{'dts:ref': div_id} for div_id in members],
        'dts:passage': f"{args.url_prefix}{args.doc_prefix}?id={args.docid}{{&ref}}",
        'dts:parent': parent
    }
    write_json_document(nav_struct, ref, level, args)
    # write default level also as toplevel
    if level == reflevel + 1:
        write_json_document(nav_struct, ref, 0, args)


def write_navigation(divs, args):
    """
    Write DTS navigation structure JSON files.
    """
    args.cite_depth = get_maxlevel(divs, 0)
    for level in range(1, args.cite_depth+1):
        # write navigation for levels
        write_nav_doc_level(divs, level, args)
       
        # write navigation for refs
        for ref in get_div_ids_upto_level(divs, level):
            write_nav_ref_level(divs, ref, level, args)
        
    
    
##
## main
##
def main():
    argp = argparse.ArgumentParser(description='Create DTSflat file structure from TEI XML.')
    argp.add_argument('--version', action='version', version='%(prog)s 1.0')
    argp.add_argument('-l', '--log', dest='loglevel', choices=['INFO', 'DEBUG', 'ERROR'], default='INFO', 
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
                      help='DTS API base URL prefix.')
    argp.add_argument('--document-prefix', dest='doc_prefix', default='/documents',
                      help='DTS document endpoint URL prefix (below base URL).')
    argp.add_argument('--navigation-prefix', dest='nav_prefix', default='/navigation',
                      help='DTS navigation endpoint URL prefix (below base URL).')
    argp.add_argument('-m', '--navigation-mode', dest='nav_mode', 
                      choices=['div', 'pb'], default='div',
                      help='Type of navigation structure: div=by tei:div.')
 
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
    logging.info(f"Parsing TEI document and creating document endpoint structure in {args.basedir}")
    info = parse_tei_doc(doc, args)
    # write navigation endpoint structure
    logging.info(f"Creating navigation endpoint structure in {args.basedir}")
    write_navigation(info, args)


if __name__ == '__main__':
    main()
