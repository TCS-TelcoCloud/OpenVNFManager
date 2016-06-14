# Copyright 2014 Tata Consultancy Services Ltd.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import netaddr
import re

from vnfsvc.common import constants
from vnfsvc.common import exceptions as n_exc
from vnfsvc.openstack.common import log as logging
from vnfsvc.openstack.common import uuidutils
from vnfsvc.openstack.common.gettextutils import _

LOG = logging.getLogger(__name__)

ATTR_NOT_SPECIFIED = object()
# Defining a constant to avoid repeating string literal in several modules
SHARED = 'shared'

# Used by range check to indicate no limit for a bound.
UNLIMITED = None


def _verify_dict_keys(expected_keys, target_dict, strict=True):
    """Allows to verify keys in a dictionary.

    :param expected_keys: A list of keys expected to be present.
    :param target_dict: The dictionary which should be verified.
    :param strict: Specifies whether additional keys are allowed to be present.
    :return: True, if keys in the dictionary correspond to the specification.
    """
    if not isinstance(target_dict, dict):
        msg = (_("Invalid input. '%(target_dict)s' must be a dictionary "
                 "with keys: %(expected_keys)s") %
               {'target_dict': target_dict, 'expected_keys': expected_keys})
        return msg

    expected_keys = set(expected_keys)
    provided_keys = set(target_dict.keys())

    predicate = expected_keys.__eq__ if strict else expected_keys.issubset

    if not predicate(provided_keys):
        msg = (_("Validation of dictionary's keys failed."
                 "Expected keys: %(expected_keys)s "
                 "Provided keys: %(provided_keys)s") %
               {'expected_keys': expected_keys,
                'provided_keys': provided_keys})
        return msg


def is_attr_set(attribute):
    return not (attribute is None or attribute is ATTR_NOT_SPECIFIED)


def _validate_values(data, valid_values=None):
    if data not in valid_values:
        msg = (_("'%(data)s' is not in %(valid_values)s") %
               {'data': data, 'valid_values': valid_values})
        LOG.debug(msg)
        return msg


def _validate_not_empty_string_or_none(data, max_len=None):
    if data is not None:
        return _validate_not_empty_string(data, max_len=max_len)


def _validate_not_empty_string(data, max_len=None):
    msg = _validate_string(data, max_len=max_len)
    if msg:
        return msg
    if not data.strip():
        return _("'%s' Blank strings are not permitted") % data


def _validate_string_or_none(data, max_len=None):
    if data is not None:
        return _validate_string(data, max_len=max_len)


def _validate_string(data, max_len=None):
    if not isinstance(data, basestring):
        msg = _("'%s' is not a valid string") % data
        LOG.debug(msg)
        return msg

    if max_len is not None and len(data) > max_len:
        msg = (_("'%(data)s' exceeds maximum length of %(max_len)s") %
               {'data': data, 'max_len': max_len})
        LOG.debug(msg)
        return msg


def _validate_boolean(data, valid_values=None):
    try:
        convert_to_boolean(data)
    except n_exc.InvalidInput:
        msg = _("'%s' is not a valid boolean value") % data
        LOG.debug(msg)
        return msg


def _validate_range(data, valid_values=None):
    """Check that integer value is within a range provided.

    Test is inclusive. Allows either limit to be ignored, to allow
    checking ranges where only the lower or upper limit matter.
    It is expected that the limits provided are valid integers or
    the value None.
    """

    min_value = valid_values[0]
    max_value = valid_values[1]
    try:
        data = int(data)
    except (ValueError, TypeError):
        msg = _("'%s' is not an integer") % data
        LOG.debug(msg)
        return msg
    if min_value is not UNLIMITED and data < min_value:
        msg = _("'%(data)s' is too small - must be at least "
                "'%(limit)d'") % {'data': data, 'limit': min_value}
        LOG.debug(msg)
        return msg
    if max_value is not UNLIMITED and data > max_value:
        msg = _("'%(data)s' is too large - must be no larger than "
                "'%(limit)d'") % {'data': data, 'limit': max_value}
        LOG.debug(msg)
        return msg


def _validate_no_whitespace(data):
    """Validates that input has no whitespace."""
    if len(data.split()) > 1:
        msg = _("'%s' contains whitespace") % data
        LOG.debug(msg)
        raise n_exc.InvalidInput(error_message=msg)
    return data



def _validate_regex(data, valid_values=None):
    try:
        if re.match(valid_values, data):
            return
    except TypeError:
        pass

    msg = _("'%s' is not a valid input") % data
    LOG.debug(msg)
    return msg


def _validate_regex_or_none(data, valid_values=None):
    if data is None:
        return
    return _validate_regex(data, valid_values)


def _validate_uuid(data, valid_values=None):
    if not uuidutils.is_uuid_like(data):
        msg = _("'%s' is not a valid UUID") % data
        LOG.debug(msg)
        return msg


def _validate_uuid_or_none(data, valid_values=None):
    if data is not None:
        return _validate_uuid(data)


def _validate_uuid_list(data, valid_values=None):
    if not isinstance(data, list):
        msg = _("'%s' is not a list") % data
        LOG.debug(msg)
        return msg

    for item in data:
        msg = _validate_uuid(item)
        if msg:
            LOG.debug(msg)
            return msg

    if len(set(data)) != len(data):
        msg = _("Duplicate items in the list: '%s'") % ', '.join(data)
        LOG.debug(msg)
        return msg


def _validate_dict_item(key, key_validator, data):
    # Find conversion function, if any, and apply it
    conv_func = key_validator.get('convert_to')
    if conv_func:
        data[key] = conv_func(data.get(key))
    val_func = val_params = None
    for (k, v) in key_validator.iteritems():
        if k.startswith('type:'):
            try:
                val_func = validators[k]
            except KeyError:
                return _("Validator '%s' does not exist.") % k
            val_params = v
            break
    # Process validation
    if val_func:
        return val_func(data.get(key), val_params)


def _validate_dict(data, key_specs=None):
    if not isinstance(data, dict):
        msg = _("'%s' is not a dictionary") % data
        LOG.debug(msg)
        return msg
    # Do not perform any further validation, if no constraints are supplied
    if not key_specs:
        return

    # Check whether all required keys are present
    required_keys = [key for key, spec in key_specs.iteritems()
                     if spec.get('required')]

    if required_keys:
        msg = _verify_dict_keys(required_keys, data, False)
        if msg:
            LOG.debug(msg)
            return msg

    # Perform validation and conversion of all values
    # according to the specifications.
    for key, key_validator in [(k, v) for k, v in key_specs.iteritems()
                               if k in data]:
        msg = _validate_dict_item(key, key_validator, data)
        if msg:
            LOG.debug(msg)
            return msg


def _validate_dict_or_none(data, key_specs=None):
    if data is not None:
        return _validate_dict(data, key_specs)


def _validate_dict_or_empty(data, key_specs=None):
    if data != {}:
        return _validate_dict(data, key_specs)


def _validate_dict_or_nodata(data, key_specs=None):
    if data:
        return _validate_dict(data, key_specs)


def _validate_non_negative(data, valid_values=None):
    try:
        data = int(data)
    except (ValueError, TypeError):
        msg = _("'%s' is not an integer") % data
        LOG.debug(msg)
        return msg

    if data < 0:
        msg = _("'%s' should be non-negative") % data
        LOG.debug(msg)
        return msg


def _validate_list_or_none(data, key_specs=None):
    if data:
       if not isinstance(data, list):
          msg = _("'%s' is not a list") % data
          LOG.debug(msg)
          return msg
       else:
          return None


def convert_to_boolean(data):
    if isinstance(data, basestring):
        val = data.lower()
        if val == "true" or val == "1":
            return True
        if val == "false" or val == "0":
            return False
    elif isinstance(data, bool):
        return data
    elif isinstance(data, int):
        if data == 0:
            return False
        elif data == 1:
            return True
    msg = _("'%s' cannot be converted to boolean") % data
    raise n_exc.InvalidInput(error_message=msg)


def convert_to_boolean_if_not_none(data):
    if data is not None:
        return convert_to_boolean(data)


def convert_to_int(data):
    try:
        return int(data)
    except (ValueError, TypeError):
        msg = _("'%s' is not a integer") % data
        raise n_exc.InvalidInput(error_message=msg)


def convert_kvp_str_to_list(data):
    """Convert a value of the form 'key=value' to ['key', 'value'].

    :raises: n_exc.InvalidInput if any of the strings are malformed
                                (e.g. do not contain a key).
    """
    kvp = [x.strip() for x in data.split('=', 1)]
    if len(kvp) == 2 and kvp[0]:
        return kvp
    msg = _("'%s' is not of the form <key>=[value]") % data
    raise n_exc.InvalidInput(error_message=msg)


def convert_kvp_list_to_dict(kvp_list):
    """Convert a list of 'key=value' strings to a dict.

    :raises: n_exc.InvalidInput if any of the strings are malformed
                                (e.g. do not contain a key) or if any
                                of the keys appear more than once.
    """
    if kvp_list == ['True']:
        # No values were provided (i.e. '--flag-name')
        return {}
    kvp_map = {}
    for kvp_str in kvp_list:
        key, value = convert_kvp_str_to_list(kvp_str)
        kvp_map.setdefault(key, set())
        kvp_map[key].add(value)
    return dict((x, list(y)) for x, y in kvp_map.iteritems())


def convert_none_to_empty_list(value):
    return [] if value is None else value


def convert_none_to_empty_dict(value):
    return {} if value is None else value


def convert_to_list(data):
    if data is None:
        return []
    elif hasattr(data, '__iter__'):
        return list(data)
    else:
        return [data]


HOSTNAME_PATTERN = ("(?=^.{1,254}$)(^(?:(?!\d+\.|-)[a-zA-Z0-9_\-]"
                    "{1,63}(?<!-)\.?)+(?:[a-zA-Z]{2,})$)")

HEX_ELEM = '[0-9A-Fa-f]'
UUID_PATTERN = '-'.join([HEX_ELEM + '{8}', HEX_ELEM + '{4}',
                         HEX_ELEM + '{4}', HEX_ELEM + '{4}',
                         HEX_ELEM + '{12}'])
# Note: In order to ensure that the MAC address is unicast the first byte
# must be even.
MAC_PATTERN = "^%s[aceACE02468](:%s{2}){5}$" % (HEX_ELEM, HEX_ELEM)

# Dictionary that maintains a list of validation functions
validators = {'type:dict': _validate_dict,
              'type:dict_or_none': _validate_dict_or_none,
              'type:dict_or_empty': _validate_dict_or_empty,
              'type:dict_or_nodata': _validate_dict_or_nodata,
              'type:non_negative': _validate_non_negative,
              'type:range': _validate_range,
              'type:regex': _validate_regex,
              'type:regex_or_none': _validate_regex_or_none,
              'type:string': _validate_string,
              'type:string_or_none': _validate_string_or_none,
              'type:not_empty_string': _validate_not_empty_string,
              'type:not_empty_string_or_none':
              _validate_not_empty_string_or_none,
              'type:uuid': _validate_uuid,
              'type:uuid_or_none': _validate_uuid_or_none,
              'type:uuid_list': _validate_uuid_list,
              'type:values': _validate_values,
              'type:boolean': _validate_boolean,
              'type:list_or_none': _validate_list_or_none}

EXT_NSES = {}

# Namespaces to be added for backward compatibility
# when existing extended resource attributes are
# provided by other extension than original one.
EXT_NSES_BC = {}




def get_attr_metadata():
    return {'xmlns': constants.XML_NS_V20,
            constants.EXT_NS: EXT_NSES,
            constants.EXT_NS_COMP: EXT_NSES_BC}
