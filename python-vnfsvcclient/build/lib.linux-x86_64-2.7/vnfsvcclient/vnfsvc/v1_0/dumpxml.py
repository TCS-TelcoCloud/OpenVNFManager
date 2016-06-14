# Copyright 2014 Tata Consultancy Services Ltd.

from vnfsvcclient.common import exceptions
from vnfsvcclient.vnfsvc import v1_0 as vnfsvcV20
from vnfsvcclient.openstack.common.gettextutils import _

_DUMPXML = 'dumpxml'


class DumpXml(vnfsvcV20.ShowCommand):
    """load xml"""
    resource = _DUMPXML
