# Copyright 2014 Tata Consultancy Services Ltd.

from vnfsvcclient.common import exceptions
from vnfsvcclient.vnfsvc import v1_0 as vnfsvcV20
from vnfsvcclient.openstack.common.gettextutils import _

_SERVICE = 'service_driver'

class ListServiceDriver(vnfsvcV20.ListCommand):
    """List service that belong to a given tenant."""
    resource = _SERVICE

class ShowServiceDriver(vnfsvcV20.ShowCommand):
    """Show information of a given VNF."""
    resource = _SERVICE
