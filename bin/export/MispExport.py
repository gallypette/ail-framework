#!/usr/bin/env python3
# -*-coding:UTF-8 -*

import os
import io
import sys
import uuid
import redis
import pdb

sys.path.append(os.path.join(os.environ['AIL_BIN'], 'export'))
sys.path.append(os.path.join(os.environ['AIL_BIN'], 'lib'))
sys.path.append(os.path.join(os.environ['AIL_BIN'], 'packages'))
import Item
import Cryptocurrency
import Pgp
import Decoded
import Domain
import Screenshot

import Correlate_object

import AILObjects
import Export


from Investigations import Investigation
import Tag

# # TODO: # FIXME: REFRACTOR ME => use UI/Global config
sys.path.append('../../configs/keys')
try:
    from mispKEYS import misp_url, misp_key, misp_verifycert
except:
    misp_url = ''
    misp_key = ''
    misp_verifycert = False

# MISP
from pymisp import MISPEvent, MISPObject, PyMISP

def is_valid_obj_to_export(obj_type, obj_subtype, obj_id):
    if not Correlate_object.is_valid_object_type(obj_type):
        return False
    if not Correlate_object.is_valid_object_subtype(obj_type, obj_subtype):
        return False
    if not Correlate_object.exist_object(obj_type, obj_id, type_id=obj_subtype):
        return False
    return True

def sanitize_obj_export_lvl(lvl):
    try:
        lvl = int(lvl)
    except:
        lvl = 0
    return lvl

def get_export_filename(json_content):
    return 'ail_export_{}.json'.format(json_content.uuid)

def create_in_memory_file(json_content):
    return io.BytesIO(json_content.encode())

def tag_misp_object_attributes(l_ref_obj_attr, tags):
    for obj_attr in l_ref_obj_attr:
        for tag in tags:
            obj_attr.add_tag(tag)

def export_ail_item(item_id, tags=[]):
    dict_metadata = Item.get_item({'id': item_id, 'date':True, 'tags':True, 'raw_content':True})[0]
    # force tags
    for tag in tags:
        if tag not in dict_metadata['tags']:
            dict_metadata['tags'].append(tag)

    #obj = MISPObject('ail-item', standalone=True)
    obj = MISPObject('ail-leak', standalone=True)
    obj.first_seen = dict_metadata['date']

    l_obj_attr = []
    l_obj_attr.append( obj.add_attribute('first-seen', value=dict_metadata['date']) )
    l_obj_attr.append( obj.add_attribute('raw-data', value=item_id, data=dict_metadata['raw_content']) )
    l_obj_attr.append( obj.add_attribute('sensor', value=Export.get_ail_uuid()) )

    # add tags
    if dict_metadata['tags']:
        tag_misp_object_attributes(l_obj_attr, dict_metadata['tags'])
    return obj

def export_domain(domain):
    domain_obj = Domain.Domain(domain)
    dict_metadata = domain_obj.get_domain_metadata(tags=True)

    # create domain-ip obj
    obj = MISPObject('domain-crawled', standalone=True)
    obj.first_seen = dict_metadata['first_seen']
    obj.last_seen = dict_metadata['last_check']

    l_obj_attr = []
    l_obj_attr.append( obj.add_attribute('domain', value=domain) )
    dict_all_url = Domain.get_domain_all_url(domain, domain_obj.get_domain_type())
    for crawled_url in dict_all_url:
        attribute = obj.add_attribute('url', value=crawled_url)
        attribute.first_seen = str(dict_all_url[crawled_url]['first_seen'])
        attribute.last_seen = str(dict_all_url[crawled_url]['last_seen'])
        l_obj_attr.append( attribute )

    # add tags
    if dict_metadata['tags']:
        tag_misp_object_attributes(l_obj_attr, dict_metadata['tags'])

    #print(obj.to_json())
    return obj

# TODO: add tags
def export_decoded(sha1_string):

    decoded_metadata = Decoded.get_decoded_metadata(sha1_string, tag=True)

    obj = MISPObject('file')
    obj.first_seen = decoded_metadata['first_seen']
    obj.last_seen = decoded_metadata['last_seen']

    l_obj_attr = []
    l_obj_attr.append( obj.add_attribute('sha1', value=sha1_string) )
    l_obj_attr.append( obj.add_attribute('mimetype', value=Decoded.get_decoded_item_type(sha1_string)) )
    l_obj_attr.append( obj.add_attribute('malware-sample', value=sha1_string, data=Decoded.get_decoded_file_content(sha1_string)) )

    # add tags
    if decoded_metadata['tags']:
        tag_misp_object_attributes(l_obj_attr, decoded_metadata['tags'])

    return obj

# TODO: add tags
def export_screenshot(sha256_string):
    obj = MISPObject('file')

    l_obj_attr = []
    l_obj_attr.append( obj.add_attribute('sha256', value=sha256_string) )
    l_obj_attr.append( obj.add_attribute('attachment', value=sha256_string, data=Screenshot.get_screenshot_file_content(sha256_string)) )

    # add tags
    tags = Screenshot.get_screenshot_tags(sha256_string)
    if tags:
        tag_misp_object_attributes(l_obj_attr, tags)

    return obj

# TODO: add tags
def export_cryptocurrency(crypto_type, crypto_address):
    dict_metadata = Cryptocurrency.cryptocurrency.get_metadata(crypto_type, crypto_address)

    obj = MISPObject('coin-address')
    obj.first_seen = dict_metadata['first_seen']
    obj.last_seen = dict_metadata['last_seen']

    l_obj_attr = []
    l_obj_attr.append( obj.add_attribute('address', value=crypto_address) )
    crypto_symbol = Cryptocurrency.get_cryptocurrency_symbol(crypto_type)
    if crypto_symbol:
        l_obj_attr.append( obj.add_attribute('symbol', value=crypto_symbol) )

    return obj

# TODO: add tags
def export_pgp(pgp_type, pgp_value):
    dict_metadata = Pgp.pgp.get_metadata(pgp_type, pgp_value)

    obj = MISPObject('pgp-meta')
    obj.first_seen = dict_metadata['first_seen']
    obj.last_seen = dict_metadata['last_seen']

    l_obj_attr = []
    if pgp_type=='key':
        l_obj_attr.append( obj.add_attribute('key-id', value=pgp_value) )
    elif pgp_type=='name':
        #l_obj_attr.append( obj.add_attribute('key-id', value='debug') )
        l_obj_attr.append( obj.add_attribute('user-id-name', value=pgp_value) )
    else: # mail
        #l_obj_attr.append( obj.add_attribute('key-id', value='debug') )
        l_obj_attr.append( obj.add_attribute('user-id-email', value=pgp_value) )
    return obj

# TODO: add tags
def export_username(username_type, username_value):
    # pdb.set_trace()
    obj = MISPObject('person')
    l_obj_attr = []
    l_obj_attr.append( obj.add_attribute('handle', value=username_value))
    l_obj_attr.append( obj.add_attribute('instant-messaging-used', value='Jabber'))

    # TODOOOO
    # compute first-seen / last-seen
    # correlations = Correlate_object.get_object_correlation('username', username_value)

    return obj


# filter objects to export, export only object who correlect which each other
def filter_obj_linked(l_obj):
    for obj in l_obj:
        res = Correlate_object.get_object_correlation(obj['type'], obj['id'], obj.get('subtype', None))
        print(res)

def add_relation_ship_to_create(set_relationship, dict_obj, dict_new_obj):
    global_id = Correlate_object.get_obj_global_id(dict_obj['type'], dict_obj['id'], dict_obj.get('subtype', None))
    global_id_new = Correlate_object.get_obj_global_id(dict_new_obj['type'], dict_new_obj['id'], dict_new_obj.get('subtype', None))
    if global_id > global_id_new:
        res = (global_id, global_id_new)
    else:
        res = (global_id_new, global_id)
    set_relationship.add( res )

# # TODO: add action by obj type
# ex => Domain
def add_obj_to_create(all_obj_to_export, set_relationship, dict_obj):
    all_obj_to_export.add(Correlate_object.get_obj_global_id(dict_obj['type'], dict_obj['id'], dict_obj.get('subtype', None)))

def add_obj_to_create_by_lvl(all_obj_to_export, set_relationship, dict_obj, lvl):
    # # TODO: filter by export mode or filter on all global ?
    if lvl >= 0:
        add_obj_to_create(all_obj_to_export, add_obj_to_create, dict_obj)

    if lvl > 0:
        lvl = lvl - 1

        # # TODO: filter by correlation types
        obj_correlations = Correlate_object.get_object_correlation(dict_obj['type'], dict_obj['id'], requested_correl_type=dict_obj.get('subtype', None))
        for obj_type in obj_correlations:
            dict_new_obj = {'type': obj_type}
            if obj_type=='pgp' or obj_type=='cryptocurrency' or obj_type=='username':
                for subtype in obj_correlations[obj_type]:
                    dict_new_obj['subtype'] = subtype
                    for obj_id in obj_correlations[obj_type][subtype]:
                        dict_new_obj['id'] = obj_id
                        add_obj_to_create_by_lvl(all_obj_to_export, set_relationship, dict_new_obj, lvl)
                        add_relation_ship_to_create(set_relationship, dict_obj, dict_new_obj)

            else:
                for obj_id in obj_correlations[obj_type]:
                    dict_new_obj['id'] = obj_id
                    add_obj_to_create_by_lvl(all_obj_to_export, set_relationship, dict_new_obj, lvl)
                    add_relation_ship_to_create(set_relationship, dict_obj, dict_new_obj)


        add_obj_to_create_by_lvl(all_obj_to_export, set_relationship, dict_obj, lvl)


def create_list_of_objs_to_export(l_obj, r_type='json'):
    all_obj_to_export = set()
    set_relationship = set()
    for obj in l_obj:
        add_obj_to_create_by_lvl(all_obj_to_export, set_relationship, obj, obj.get('lvl', 1))

    # create MISP objects
    dict_misp_obj = create_all_misp_obj(all_obj_to_export, set_relationship)

    # create object relationships
    for obj_global_id_1, obj_global_id_2 in set_relationship:
        dict_relationship = get_relationship_between_global_obj(obj_global_id_1, obj_global_id_2)
        if dict_relationship:
            obj_src = dict_misp_obj[dict_relationship['src']]
            obj_dest = dict_misp_obj[dict_relationship['dest']]
            obj_src.add_reference(obj_dest.uuid, dict_relationship['relation'], 'add a comment')

    event = MISPEvent()
    event.info = 'AIL framework export'
    event.uuid = str(uuid.uuid4())
    for obj_global_id in dict_misp_obj:
        misp_obj = dict_misp_obj[obj_global_id]
        AILObjects.create_map_obj_event_uuid(event.uuid, obj_global_id)
        AILObjects.create_map_obj_uuid_golbal_id(event.uuid, obj_global_id)
        if misp_obj:
            # add object to event
            event.add_object(dict_misp_obj[obj_global_id])

    return event

def create_all_misp_obj(all_obj_to_export, set_relationship):
    dict_misp_obj = {}
    for obj_global_id in all_obj_to_export:
        obj_type, obj_id = obj_global_id.split(':', 1)
        dict_misp_obj[obj_global_id] = create_misp_obj(obj_type, obj_id)

    return dict_misp_obj

def create_misp_obj(obj_type, obj_id):
    if obj_type == 'item':
        return export_ail_item(obj_id)
    elif obj_type == 'decoded':
        return export_decoded(obj_id)
    elif obj_type == 'image':
        return export_screenshot(obj_id)
    elif obj_type == 'cryptocurrency':
        obj_subtype, obj_id = obj_id.split(':', 1)
        return export_cryptocurrency(obj_subtype, obj_id)
    elif obj_type == 'pgp':
        obj_subtype, obj_id = obj_id.split(':', 1)
        return export_pgp(obj_subtype, obj_id)
    elif obj_type == 'domain':
        return export_domain(obj_id)
    elif obj_type == 'username':
        obj_subtype, obj_id = obj_id.split(':', 1)
        return export_username(obj_subtype, obj_id)

def get_relationship_between_global_obj(obj_global_id_1, obj_global_id_2):
    obj_type_1 = obj_global_id_1.split(':', 1)[0]
    obj_type_2 = obj_global_id_2.split(':', 1)[0]
    type_tuple = [obj_type_1, obj_type_2]

    if 'image' in type_tuple: # or screenshot ## TODO:
        if obj_type_1 == 'image':
            src = obj_global_id_1
            dest = obj_global_id_2
        else:
            src = obj_global_id_2
            dest = obj_global_id_1
        return {'relation': 'screenshot-of', 'src': src, 'dest': dest}
    elif 'decoded' in type_tuple:
        if obj_type_1 == 'decoded':
            src = obj_global_id_1
            dest = obj_global_id_2
        else:
            src = obj_global_id_2
            dest = obj_global_id_1
        return {'relation': 'included-in', 'src': src, 'dest': dest}
    elif 'pgp' in type_tuple:
        if obj_type_1 == 'pgp':
            src = obj_global_id_1
            dest = obj_global_id_2
        else:
            src = obj_global_id_2
            dest = obj_global_id_1
        return {'relation': 'extracted-from', 'src': src, 'dest': dest}
    elif 'cryptocurrency':
        if obj_type_1 == 'cryptocurrency':
            src = obj_global_id_1
            dest = obj_global_id_2
        else:
            src = obj_global_id_2
            dest = obj_global_id_1
        return {'relation': 'extracted-from', 'src': src, 'dest': dest}
    elif 'domain' in type_tuple:
        if 'item' in type_tuple:
            if obj_type_1 == 'item':
                src = obj_global_id_1
                dest = obj_global_id_2
            else:
                src = obj_global_id_2
                dest = obj_global_id_1
            return {'relation': 'extracted-from', 'src': src, 'dest': dest} # replave by crawled-from
    elif 'item' in type_tuple:
        if 'domain' in type_tuple:
            if obj_type_1 == 'item':
                src = obj_global_id_1
                dest = obj_global_id_2
            else:
                src = obj_global_id_2
                dest = obj_global_id_1
            return {'relation': 'extracted-from', 'src': src, 'dest': dest} # replave by crawled-from
    return None

def sanitize_event_distribution(distribution):
    try:
        int(distribution)
        if (0 <= distribution <= 3):
            return distribution
        else:
            return 0
    except:
        return 0

def sanitize_event_threat_level_id(threat_level_id):
    try:
        int(threat_level_id)
        if (1 <= threat_level_id <= 4):
            return threat_level_id
        else:
            return 4
    except:
        return 4

def sanitize_event_analysis(analysis):
    try:
        int(analysis)
        if (0 <= analysis <= 2):
            return analysis
        else:
            return 0
    except:
        return 0

# # TODO: return error
def ping_misp():
    try:
        PyMISP(misp_url, misp_key, misp_verifycert)
        return True
    except Exception as e:
        print(e)
        return False

def create_misp_event(event, distribution=0, threat_level_id=4, publish=False, analysis=0, event_info=None):
    if event_info:
        event.info = event_info
    event.distribution = sanitize_event_distribution(distribution)
    event.threat_level_id = sanitize_event_threat_level_id(threat_level_id)
    event.analysis = sanitize_event_analysis(analysis)
    if publish:
        event.publish()

    # # TODO: handle multiple MISP instance
    misp = PyMISP(misp_url, misp_key, misp_verifycert)
    #print(event.to_json())

    misp_event = misp.add_event(event)
     #print(misp_event)
    # # TODO: handle error
    event_metadata = extract_event_metadata(misp_event)
    return event_metadata

def extract_event_metadata(event):
    event_metadata = {}
    event_metadata['uuid'] = event['Event']['uuid']
    event_metadata['id'] = event['Event']['id']
    if misp_url[-1] == '/':
        event_metadata['url'] = misp_url + 'events/view/' + str(event_metadata['id'])
    else:
        event_metadata['url'] = misp_url + '/events/view/' + str(event_metadata['id'])
    return event_metadata

######
#
# EXPORT LVL DEFINITION: (== Correl<tion DEPTH)
#
# LVL 0 => PARTIAL    Only add core item Correlation
# LVL 1 => DETAILED   Also add correlated_items correlation
######

# # TODO: # create object relationships
def create_investigation_event(investigation_uuid):
    investigation = Investigation(investigation_uuid)

    event = MISPEvent()
    event.info = investigation.get_info()
    event.uuid = investigation.get_uuid(separator=True)
    event.date = investigation.get_date()
    event.analysis = investigation.get_analysis()
    event.threat_level_id = investigation.get_threat_level()

    event.distribution = 0

    # tags
    for tag in investigation.get_tags():
        event.add_tag(tag)
    # objects
    investigation_objs = investigation.get_objects()
    for obj in investigation_objs:
        # if subtype -> obj_id = 'subtype:type'
        if obj['subtype']:
            obj_id = f"{obj['subtype']}:{obj['id']}"
        else:
            obj_id = obj['id']
        misp_obj = create_misp_obj(obj['type'], obj_id)
        if misp_obj:
            event.add_object(misp_obj)

    # if publish:
    #     event.publish()

    # print(event.to_json())
    misp = PyMISP(misp_url, misp_key, misp_verifycert)
    if misp.event_exists(event.uuid):
        misp_event = misp.update_event(event)
    else:
        misp_event = misp.add_event(event)

    # # TODO: handle error
    event_metadata = extract_event_metadata(misp_event)
    if event_metadata.get('uuid'):
        if misp_url[-1] == '/':
            url =  misp_url[:-1]
        else:
            url =  misp_url
        investigation.add_misp_events(url)
    return event_metadata

# if __name__ == '__main__':

    # l_obj = [{'id': 'bfd5f1d89e55b10a8b122a9d7ce31667ec1d086a', 'type': 'decoded', 'lvl': 2}]
    # create_list_of_objs_to_export(l_obj)

    #print(event.to_json())
