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

def add_set_attr(obj, attr, val):
    curval = getattr(obj, attr)
    if curval is None:
        setattr(obj, attr, val)
    else:
        setattr(obj, attr, curval + val)

    
def ns_pref_name(prefix, lname):
    """
    Return etree format name from prefix and local name.
    """
    return f"{{{XMLNS[prefix]}}}{lname}"


def ns_uri_name(ns, lname):
    """
    Returns etree format name from namespace uri and local name.
    """
    if ns is None or ns == XMLNS['']:
        # no ns or default ns
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


def write_xml_fragment(doc, frag_id, args, wrap_dts_frag=True):
    """
    Write fragment doc as XML file in structured directories starting at basedir.
    
    Directory structure: basedir/docid/frag_id/tei-frag.xml
    """
    dir = Path(args.basedir, args.docid, frag_id)
    dir.mkdir(parents=True, exist_ok=True)
    outfile = Path(dir, 'tei-frag.xml')
    logging.debug(f"writing XML fragment {outfile}")
    with outfile.open(mode='wb') as f:
        if wrap_dts_frag:
            # root fragment_root TEI
            tei = ET.Element('TEI')
            # dts:fragment wrapper around fragment doc
            frag = ET.SubElement(tei, ns_pref_name('dts', 'fragment'))
            frag.append(doc)
            doc = tei
            
        # write as new ElementTree
        tree = ET.ElementTree(doc)
            
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
    div_id = doc.get(ns_pref_name('xml', 'id'))
    if div_id is None:
        # create and set new id
        div_id = f"{args.genid_prefix}-div{args.genid_cnt}"
        args.genid_cnt += 1
        doc.set(ns_pref_name('xml', 'id'), div_id)
        
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
    if doc.tag != ns_pref_name('', 'TEI'):
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
        infos = parse_tei_pbs(doc, args)
        
    else:
        raise RuntimeError(f"Invalid navigation mode {args.nav_mode}")
    
    return infos



def parse_tei_pbs(doc, args):
    """
    Parse TEI document in args.inputfile for pb elements.
    
    Writes XML fragments between pb elements.
    Returns list of info structures from pbs. 
    """
    
    class TeiPbProcessor(xml.sax.handler.ContentHandler):
        """SAX parser for processing tei:pb elements"""
    
        def __init__(self, facs_dict={}, args=None):
            self.args = args
            self.facs_dict = facs_dict
            self.pbs = []
            self.current_content = ''
            self.current_element = None
            self.current_parents = []
            self.open_tags = []
            self.prev_event_close = False
            self.prev_element = None
            self.pb_cnt = 0


        def create_etree_attrs(self, sax_attrs):
            """Create etree attribute dict from sax attribute object."""
            _sax_attrs = dict(sax_attrs)
            return {ns_uri_name(k[0], k[1]): _sax_attrs[k] for k in _sax_attrs}


        def create_etree_elem(self, sax_name, attrs):
            """Create etree Element from sax_name and etree attrs."""
            ns, lname = sax_name
            elem = ET.Element(ns_uri_name(sax_name[0], sax_name[1]), attrib=attrs)
            return elem

    
        def start_etree_fragment(self, facs_id=None):
            """
            Create new etree fragment as current fragment.
            
            Includes facsimile fragment for facs_id.
            Includes empty tag hierarchy from open_tags and dts:fragment.
            """ 
            root_elem = ET.Element('TEI')
            self.current_element = root_elem
            self.current_parents = []
            if facs_id in self.facs_dict:
                # add facsimile with matching element
                fm_elem = ET.Element('facsimile')
                fm_elem.append(self.facs_dict[facs_id])
                root_elem.append(fm_elem)
                
            # create empty tags from open_tags
            for t in self.open_tags:
                if t['lname'] == 'TEI':
                    continue
                
                elem = ET.Element(ns_uri_name(t['ns'], t['lname']), attrib=t['attrs'])
                # append elem to current element
                self.current_element.append(elem)
                # push current to parent list
                self.current_parents.append(self.current_element)
                self.current_element = elem

            # add dts:fragment wrapper
            frag = ET.Element(ns_pref_name('dts', 'fragment'))
            self.current_element.append(frag)
            self.current_parents.append(self.current_element)
            self.current_element = frag

    
        def write_etree_fragment(self, frag_id):
            """Write current fragment as frag_id."""
            write_xml_fragment(self.current_parents[0], frag_id, self.args, wrap_dts_frag=False)

    
        def startElementNS(self, name, qname, sax_attrs):
            # save remaining content
            if len(self.current_content) > 0:
                if self.prev_event_close:
                    # start after previous end
                    add_set_attr(self.prev_element, 'tail', self.current_content)
                else:
                    # start after previous start
                    add_set_attr(self.current_element, 'text', self.current_content)
                    
                self.current_content = ''
                
            ns, lname = name
            attrs = self.create_etree_attrs(sax_attrs)
            elem = self.create_etree_elem(name, attrs)
            if lname == 'pb':
                # write previous fragment
                if len(self.pbs) > 0:
                    self.write_etree_fragment(self.pbs[-1]['id'])
                    
                # start new fragment
                self.pb_cnt += 1
                pb_id = f"pb-{self.pb_cnt}"
                facs = sax_attrs.getValueByQName('facs')
                facs_id = None
                if not facs:
                    logging.warning("pb tag without facs attribute")
                elif facs.startswith('#'):
                    # facs is reference to surface
                    facs_id = facs[1:]

                self.start_etree_fragment(facs_id=facs_id)
                self.pbs.append({'id': pb_id, 'level': 1, 'facs': facs, 'attrs': attrs})
                
            # append new elem to current fragment
            if self.current_element is not None:
                # append to parent element
                self.current_element.append(elem)
                
            # push current to parent list
            self.current_parents.append(self.current_element)
            # set new elem as current
            self.current_element = elem
            self.open_tags.append({'ns':ns, 'lname': lname, 'attrs': attrs})
            self.prev_event_close = False

    
        def characters(self, content):
            self.current_content += content

    
        def endElementNS(self, name, qname):
            # set current content as element text or previous element tail
            if len(self.current_content) > 0:
                if self.prev_event_close:
                    # start after previous end
                    add_set_attr(self.prev_element, 'tail', self.current_content)
                else:
                    # start after previous start
                    add_set_attr(self.current_element, 'text', self.current_content)
                    
                self.current_content = ''

            self.prev_element = self.current_element
            # close current element
            self.open_tags.pop()
            self.current_element = self.current_parents.pop()
            if self.current_element is None:
                logging.warning(f"empty stack after closing element {name}")

            self.prev_event_close = True

                
        def endDocument(self):
            # TODO: save last fragment
            pass

    
        def get_pb_info(self):
            return self.pbs

    # read facs_dict element
    facs_dict = {}
    for elem in doc.find('facsimile', XMLNS):
        elem_id = elem.get(ns_pref_name('xml', 'id'))
        if elem_id:
            facs_dict[elem_id] = elem
            
    # create SAX parser
    parser = xml.sax.make_parser()
    parser.setFeature(xml.sax.handler.feature_namespaces, True)
    # set our handler
    handler = TeiPbProcessor(facs_dict=facs_dict, args=args)
    parser.setContentHandler(handler)
    # parse XML file
    parser.parse(args.inputfile)
    # return output from handler
    info = handler.get_pb_info()
    return info


def get_maxlevel(divs, maxlevel):
    """
    Returns the maximum div level.
    """
    for info in divs:
        if info['level'] > maxlevel:
            maxlevel = info['level']
            
        if info.get('subdivs', None):
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

        if div.get('subdivs', None):
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
            
        if div.get('subdivs', None):
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

        if div.get('subdivs', None):
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
    argp.add_argument('--version', action='version', version='%(prog)s 1.2')
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
