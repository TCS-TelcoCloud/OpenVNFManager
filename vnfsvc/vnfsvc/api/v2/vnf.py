# Copyright 2014 Tata Consultancy Services Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import abc

import six

from vnfsvc.api.v2 import attributes as attr
from vnfsvc.api.v2 import resource_helper
from vnfsvc.common import exceptions
from vnfsvc.openstack.common import log as logging
from vnfsvc.openstack.common.gettextutils import _

LOG = logging.getLogger(__name__)


class VNFDriverNotSpecified(exceptions.InvalidInput):
    message = _('vnf driver is not speicfied')


class MgmtDriverNotSpecified(exceptions.InvalidInput):
    message = _('management driver is not speicfied')


class ServiceTypeNotSpecified(exceptions.InvalidInput):
    message = _('service types are not speicfied')


class VNFTemplateInUse(exceptions.InUse):
    message = _('vnf template %(vnf_template_id)s is still in use')


class VNFInUse(exceptions.InUse):
    message = _('VNF %(vnf_id)s is still in use')


class InvalidVNFDriver(exceptions.InvalidInput):
    message = _('invalid name for vnf driver %(vnf_driver)s')


class InvalidMgmtDriver(exceptions.InvalidInput):
    message = _('invalid name for management driver %(mgmt_driver)s')


class InvalidServiceType(exceptions.InvalidInput):
    message = _('invalid service type %(service_type)s')


class VNFCreateFailed(exceptions.VNFSvcException):
    message = _('creating vnf based on %(vnf_template_id)s failed')


class VNFCreateWaitFailed(exceptions.VNFSvcException):
    message = _('waiting for creation of vnf %(vnf_id)s failed')


class VNFDeleteFailed(exceptions.VNFSvcException):
    message = _('deleting vnf %(vnf_id)s failed')


class VNFTemplateNotFound(exceptions.NotFound):
    message = _('vnf template %(vnf_tempalte_id)s could not be found')


class SeviceTypeNotFound(exceptions.NotFound):
    message = _('service type %(service_type_id)s could not be found')


class VNFNotFound(exceptions.NotFound):
    message = _('vnf %(vnf_id)s could not be found')


def _validate_service_context_list(data, valid_values=None):
    if not isinstance(data, list):
        msg = _("invalid data format for service context list: '%s'") % data
        LOG.debug(msg)
        return msg

    key_specs = {
        'network_id': {'type:uuid': None},
        'subnet_id': {'type:uuid': None},
        'port_id': {'type:uuid': None},
        'role': {'type:string': None},
    }
    for sc_entry in data:
        msg = attr._validate_dict_or_empty(sc_entry, key_specs=key_specs)
        if msg:
            LOG.debug(msg)
            return msg


attr.validators['type:service_context_list'] = _validate_service_context_list


RESOURCE_ATTRIBUTE_MAP = {

    'services': {
         'tenant_id': {
             'allow_post': True,
             'allow_put': False,
             'validate': {'type:string': None},
             'required_by_policy': True,
             'is_visible': True,
         },
         'name': {
             'allow_post': True,
             'allow_put': True,
             'validate': {'type:string': None},
             'is_visible': True,
             'default': '',
         },
         'description': {
              'allow_post': True,
              'allow_put': True,
              'validate': {'type:string': None},
              'is_visible': True,
              'default': '',
         },
         'quality_of_service': {
             'allow_post': True,
             'allow_put': True,
             'validate': {'type:string': None},
             'default' : '',
             'is_visible': True,
             'default': '',
         },
         'attributes': {
            'allow_post': True,
            'allow_put': True,
            'validate': {'type:dict_or_none': None},
            'is_visible': True,
            'default': {},
         },

    },
    'templates': {
         'tenant_id': {
             'allow_post': True,
             'allow_put': False,
             'validate': {'type:string': None},
             'required_by_policy': True,
             'is_visible': True,
         },
         'name': {
             'allow_post': True,
             'allow_put': True,
             'validate': {'type:string': None},
             'is_visible': True,
             'default': '',
         },
         'files': {
             'allow_post': True,
             'allow_put': False,
             'validate': {'type:dict_or_none': None},
             'required_by_policy': True,
             'is_visible': True,
         },
    },

    'activates': {
         'tenant_id': {
             'allow_post': True,
             'allow_put': False,
             'validate': {'type:string': None},
             'required_by_policy': True,
             'is_visible': True,
         },
         'name': {
             'allow_post': True,
             'allow_put': True,
             'validate': {'type:string': None},
             'is_visible': True,
             'default': '',
         },
         'template_id': {
             'allow_post': True,
             'allow_put': True,
             'validate': {'type:string': None},
             'is_visible': True,
             'default': '',
         },

         'enable': {
             'allow_post': True,
             'allow_put': True,
             'validate': {'type:string': None},
             'is_visible': True,
             'default': '',
         },
     },
    'diagnostics':{
         'tenant_id': {
             'allow_post': True,
             'allow_put': False,
             'validate': {'type:string': None},
             'required_by_policy': True,
             'is_visible': True,
         },
         'nsd_id': {
             'allow_post': True,
             'allow_put': False,
             'validate': {'type:string': None},
             'is_visible': True,
         },
         'vdus': {
            'allow_post': True,
            'allow_put': True,
            'validate': {'type:list_or_none': None},
            'is_visible': True,
            'default': {},
         },
    },

    'configurations':{
         'attributes': {
            'allow_post': True,
            'allow_put': True,
            'validate': {'type:dict_or_none': None},
            'is_visible': True,
            'default': {},
         },

    },

    'dumxmls': {
         'tenant_id': {
             'allow_post': True,
             'allow_put': False,
             'validate': {'type:string': None},
             'required_by_policy': True,
             'is_visible': True,
         },
         'name': {
             'allow_post': True,
             'allow_put': True,
             'validate': {'type:string': None},
             'is_visible': True,
             'default': '',
         },
    },
    'registers': {
        'tenant_id': {
            'allow_post': True,
            'allow_put': False,
            'validate': {'type:string': None},
            'required_by_policy': True,
            'is_visible': True,
        },
        'user': {
            'allow_post': True,
            'allow_get': False,
            'validate': {'type:dict_or_none': None},
            'is_visible': True
        }
    },
}
