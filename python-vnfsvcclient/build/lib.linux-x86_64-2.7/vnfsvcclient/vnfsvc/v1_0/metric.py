from vnfsvcclient.common import exceptions
from vnfsvcclient.vnfsvc import v1_0 as vnfsvcV20
from vnfsvcclient.openstack.common.gettextutils import _
from vnfsvcclient.common.yamlutil import ordered_load
import zipfile
import tempfile
import yaml
import json
import os

_METRIC = 'metric'

class ListMetric(vnfsvcV20.ListCommand):
    """List templates."""
    resource = _METRIC

class ShowMetric(vnfsvcV20.ShowCommand):
    """Show information of a given VNF."""
    resource = _METRIC

